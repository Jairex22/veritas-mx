"""BM25 en Python: respaldo cuando SQLite no tiene FTS5."""
from __future__ import annotations

import math
from collections import Counter

from core.text import term_key, tokenize


class BM25:
    def __init__(self, documents: list[tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        """documents: lista de (id, texto)."""
        self.k1, self.b = k1, b
        self.ids = [doc_id for doc_id, _ in documents]
        self.tfs: list[Counter[str]] = []
        df: Counter[str] = Counter()
        for _, text in documents:
            keys = [term_key(t) for t in tokenize(text)]
            tf = Counter(keys)
            self.tfs.append(tf)
            df.update(tf.keys())
        self.n = len(documents)
        self.avgdl = (sum(sum(tf.values()) for tf in self.tfs) / self.n) if self.n else 0.0
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, terms: list[str], limit: int) -> list[tuple[str, float]]:
        keys = list(dict.fromkeys(term_key(t) for t in terms))
        scores = []
        for doc_id, tf in zip(self.ids, self.tfs):
            dl = sum(tf.values()) or 1
            score = 0.0
            for key in keys:
                freq = tf.get(key, 0)
                if not freq:
                    continue
                idf = self.idf.get(key, 0.0)
                score += idf * freq * (self.k1 + 1) / (freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if score > 0:
                scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:limit]
