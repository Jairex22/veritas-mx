"""Proveedores de embeddings locales.

- `HashingEmbedder` (por defecto): vectores dispersos proyectados por hashing de palabras, bigramas y
  n-gramas de caracteres. 100 % local, sin descargas, determinista. Captura similitud léxica difusa
  (variantes, acentos, plurales) pero NO semántica profunda. La cobertura bilingüe se apoya en el
  glosario de sinónimos (config/rules.yaml).
- `SentenceTransformerEmbedder` (opcional): modelo multilingüe local (p. ej.
  paraphrase-multilingual-MiniLM-L12-v2) copiado manualmente a models_local/. Se carga en modo
  offline (HF_HUB_OFFLINE=1); si no está instalado o no existe la carpeta, se usa hashing.
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import Protocol

import numpy as np

from core.logging_setup import get_logger
from core.text import STOPWORDS, tokenize

log = get_logger("embeddings")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 768):
        self.dim = int(dim)
        self.name = f"hashing-v1-{self.dim}"

    def _features(self, text: str) -> dict[int, float]:
        feats: dict[int, float] = {}

        def add(feature: str, weight: float) -> None:
            h = zlib.crc32(feature.encode("utf-8"))
            idx = h % self.dim
            sign = 1.0 if (h >> 31) & 1 == 0 else -1.0
            feats[idx] = feats.get(idx, 0.0) + sign * weight

        tokens = [t for t in tokenize(text) if t not in STOPWORDS]
        for tok in tokens:
            add("w:" + tok, 1.0)
            padded = f"<{tok}>"
            if len(tok) > 3:
                for i in range(len(padded) - 3):
                    add("c:" + padded[i:i + 4], 0.25)
        for a, b in zip(tokens, tokens[1:]):
            add(f"b:{a}_{b}", 0.5)
        return feats

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for idx, value in self._features(text).items():
                matrix[row, idx] = value
        # escalamiento sublineal y normalización L2
        matrix = np.sign(matrix) * np.log1p(np.abs(matrix))
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms


class SentenceTransformerEmbedder:
    def __init__(self, model_dir: Path):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer  # importación opcional

        self.model = SentenceTransformer(str(model_dir), device="cpu")
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.name = f"st-{model_dir.name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


def build_embedder(provider: str, model_dir: Path, dim: int) -> tuple[Embedder, list[str]]:
    """Devuelve (embedder, advertencias). Nunca falla: degrada a hashing."""
    warnings: list[str] = []
    if provider == "sentence_transformers":
        if not model_dir.is_dir():
            warnings.append("Modelo de embeddings local no encontrado; se usa hashing.")
        else:
            try:
                return SentenceTransformerEmbedder(model_dir), warnings
            except Exception as exc:  # noqa: BLE001 - dependencia opcional; degradar con aviso
                log.warning("sentence-transformers no disponible: %s", type(exc).__name__)
                warnings.append("sentence-transformers no disponible; se usa hashing.")
    return HashingEmbedder(dim), warnings
