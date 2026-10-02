"""Recuperación híbrida: BM25 (FTS5 o Python) + vectores locales + filtros + fusión RRF + reranking."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from core.utils import today
from models.domain import RetrievedChunk, SearchFilters, SourceType
from rag.embeddings import Embedder
from rag.lexical import BM25
from rag.query import Glossary, QueryTerms, analyze, coverage
from repositories.chunks import ChunkRepository


@dataclass
class RetrievalResult:
    hits: list[RetrievedChunk]
    query: QueryTerms
    eligible_count: int
    lexical_count: int = 0
    vector_count: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class _EligibleSet:
    rows: list[dict[str, Any]]
    matrix: np.ndarray | None
    index_of: dict[str, int]
    bm25: BM25 | None = None


class HybridRetriever:
    def __init__(self, chunks: ChunkRepository, embedder: Embedder, glossary: Glossary, *, top_k: int = 6,
                 candidate_pool: int = 40, rrf_k: int = 60, rerank: bool = True, cache_size: int = 32):
        self.chunks = chunks
        self.embedder = embedder
        self.glossary = glossary
        self.top_k = top_k
        self.candidate_pool = candidate_pool
        self.rrf_k = rrf_k
        self.rerank = rerank
        self._cache: OrderedDict[tuple, _EligibleSet] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self.index_version = 0

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self.index_version += 1

    def _eligible(self, clearance: tuple[str, ...], filters: SearchFilters | None,
                  include_version_ids: tuple[str, ...]) -> _EligibleSet:
        key = (clearance, tuple(sorted((filters.active() if filters else {}).items())), include_version_ids,
               today().isoformat(), self.index_version)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        rows = self.chunks.eligible(clearance, filters, today().isoformat(), include_version_ids)
        vectors, index_of = [], {}
        for row in rows:
            blob = row.pop("embedding", None)
            if blob:
                vec = np.frombuffer(blob, dtype=np.float32)
                if vec.shape[0] == self.embedder.dim:
                    index_of[row["chunk_id"]] = len(vectors)
                    vectors.append(vec)
        matrix = np.vstack(vectors) if vectors else None
        bm25 = None
        if not self.chunks.db.has_fts5:
            bm25 = BM25([(r["chunk_id"], f"{r['title']} {r['section']} {r['text']}") for r in rows])
        eligible = _EligibleSet(rows=rows, matrix=matrix, index_of=index_of, bm25=bm25)
        with self._lock:
            self._cache[key] = eligible
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return eligible

    def retrieve(self, question: str, clearance: Iterable[str], filters: SearchFilters | None = None,
                 include_version_ids: Iterable[str] = (), top_k: int | None = None) -> RetrievalResult:
        query = analyze(question, self.glossary)
        eligible = self._eligible(tuple(sorted(clearance)), filters, tuple(sorted(include_version_ids)))
        if not eligible.rows or not query.concepts:
            return RetrievalResult(hits=[], query=query, eligible_count=len(eligible.rows))
        by_id = {r["chunk_id"]: r for r in eligible.rows}
        search_terms = list(dict.fromkeys(query.original + query.search_terms))

        # 1) Léxico
        if eligible.bm25 is not None:
            lexical = eligible.bm25.search(search_terms, self.candidate_pool)
        else:
            lexical = [(cid, s) for cid, s in self.chunks.fts_search(search_terms, self.candidate_pool * 5)
                       if cid in by_id][: self.candidate_pool]

        # 2) Vectorial
        vector: list[tuple[str, float]] = []
        cosine: dict[str, float] = {}
        if eligible.matrix is not None:
            qvec = self.embedder.embed([f"{question} {query.expansion_text}"])[0]
            sims = eligible.matrix @ qvec
            ids = list(eligible.index_of)
            for cid, idx in eligible.index_of.items():
                cosine[cid] = float(sims[idx])
            order = np.argsort(-sims)[: self.candidate_pool]
            vector = [(ids[i], float(sims[i])) for i in order if sims[i] > 0]

        # 3) Fusión RRF
        fused: dict[str, float] = {}
        for ranking in (lexical, vector):
            for rank, (cid, _) in enumerate(ranking, start=1):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (self.rrf_k + rank)
        if not fused:
            return RetrievalResult(hits=[], query=query, eligible_count=len(eligible.rows))
        max_fused = max(fused.values())
        lex_scores = dict(lexical)
        active_filters = filters.active() if filters else {}

        hits: list[RetrievedChunk] = []
        for cid, fscore in fused.items():
            row = by_id[cid]
            cov = coverage(query, f"{row['title']} {row['section']} {row['text']}")
            cos = max(0.0, cosine.get(cid, 0.0))
            relevance = 0.65 * cov + 0.35 * min(1.0, cos / 0.6)
            try:
                authority = SourceType(row["source_type"]).authority
            except ValueError:
                authority = 0.5
            filter_boost = 0.0
            if active_filters:
                matches = sum(1 for k, v in active_filters.items()
                              if str(row.get("fl_module" if k == "module" else k, "")).lower() == v.lower())
                filter_boost = matches / len(active_filters)
            if self.rerank:
                final = 0.6 * relevance + 0.15 * authority + 0.15 * (fscore / max_fused) + 0.1 * filter_boost
            else:
                final = fscore / max_fused
            hits.append(RetrievedChunk(
                chunk_id=cid, document_id=row["document_id"], version_id=row["version_id"],
                doc_code=row["doc_code"], title=row["title"], version_label=row["version_label"],
                source_type=row["source_type"], classification=row["classification"], section=row["section"],
                page=row["page"], text=row["text"], effective_date=row["effective_date"],
                review_date=row["review_date"], expiration_date=row["expiration_date"], owner=row["owner"],
                is_demo=bool(row["is_demo"]), injection_flag=bool(row["injection_flag"]),
                fl_module=row["fl_module"], lexical_score=lex_scores.get(cid, 0.0), vector_score=cos,
                fused_score=fscore, coverage=cov, relevance=relevance, final_score=final))
        hits.sort(key=lambda h: (-h.final_score, h.priority))
        return RetrievalResult(hits=hits[: top_k or self.top_k], query=query, eligible_count=len(eligible.rows),
                               lexical_count=len(lexical), vector_count=len(vector))
