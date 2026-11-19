from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray:
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self.dimension = 384

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
                self.dimension = int(self._model.get_sentence_embedding_dimension())
                self.backend = "sentence-transformers"
            except Exception as exc:
                from app.rag.minilm import MiniLMNumpy

                logger.warning(
                    "PyTorch could not load (%s). Using the published all-MiniLM-L6-v2 weights directly.",
                    exc,
                )
                self._model = MiniLMNumpy(self.model_name)
                self.dimension = 384
                self.backend = "numpy-minilm"
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype="float32")
        model = self._load()
        if hasattr(model, "encode"):
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return np.asarray(vectors, dtype="float32")
        return model.embed(texts)


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix /= norms
    return matrix


def _import_faiss():
    try:
        import faiss

        return faiss
    except Exception as exc:
        logger.warning(
            "FAISS could not be loaded (%s). Search will use a NumPy inner-product index.",
            exc,
        )
        return None


class VectorIndex:
    def __init__(self) -> None:
        self.index = None
        self.vectors: np.ndarray | None = None
        self.metas: list[dict] = []
        self.dimension = 0

    @property
    def ready(self) -> bool:
        return self.vectors is not None and len(self.vectors) > 0

    def build(self, vectors: np.ndarray, metas: list[dict]) -> None:
        if len(metas) != len(vectors):
            raise ValueError("Embedding rows and metadata rows do not match")
        if len(vectors) == 0:
            self.index = None
            self.vectors = None
            self.metas = []
            self.dimension = 0
            return
        matrix = np.ascontiguousarray(vectors.astype("float32"))
        _normalize(matrix)
        self.vectors = matrix
        self.metas = metas
        self.dimension = int(matrix.shape[1])
        self.index = None
        faiss = _import_faiss()
        if faiss is not None:
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            self.index = index

    def save(self, index_path: Path, meta_path: Path) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(self.metas, ensure_ascii=False), encoding="utf-8")
        vector_path = index_path.with_suffix(".npy")
        if self.vectors is None:
            if vector_path.exists():
                vector_path.unlink()
            if index_path.exists():
                index_path.unlink()
            return
        np.save(vector_path, self.vectors)
        if self.index is not None:
            faiss = _import_faiss()
            if faiss is not None:
                faiss.write_index(self.index, str(index_path))

    def load(self, index_path: Path, meta_path: Path) -> bool:
        self.index = None
        self.vectors = None
        self.metas = []
        if not meta_path.exists():
            return False
        self.metas = json.loads(meta_path.read_text(encoding="utf-8"))
        vector_path = index_path.with_suffix(".npy")
        if vector_path.exists():
            self.vectors = np.load(vector_path)
            self.dimension = int(self.vectors.shape[1]) if len(self.vectors) else 0
        if index_path.exists():
            faiss = _import_faiss()
            if faiss is not None:
                self.index = faiss.read_index(str(index_path))
                self.dimension = int(self.index.d)
                if self.vectors is None and self.index.ntotal:
                    self.vectors = np.vstack([self.index.reconstruct(i) for i in range(self.index.ntotal)])
        if self.vectors is not None and len(self.metas) != len(self.vectors):
            logger.warning("Index metadata does not match the vector rows. The index will be ignored.")
            self.vectors = None
            self.metas = []
            self.index = None
        return self.ready

    def search(
        self,
        vector: np.ndarray,
        *,
        top_k: int,
        threshold: float,
        source: str | None = None,
        category: str | None = None,
        location: str | None = None,
        property_type: str | None = None,
    ) -> list[dict]:
        if not self.ready or self.vectors is None:
            return []
        query = np.ascontiguousarray(vector.astype("float32").reshape(1, -1))
        _normalize(query)
        fetch = min(len(self.vectors), max(top_k * 8, top_k))
        if self.index is not None:
            scores, ids = self.index.search(query, fetch)
            pairs = list(zip(scores[0].tolist(), ids[0].tolist()))
        else:
            ranked = self.vectors @ query[0]
            order = np.argsort(-ranked)[:fetch]
            pairs = [(float(ranked[i]), int(i)) for i in order]
        hits: list[dict] = []
        for score, row_id in pairs:
            if row_id < 0 or float(score) < threshold:
                continue
            meta = dict(self.metas[int(row_id)])
            if not _matches(meta, source, category, location, property_type):
                continue
            meta["score"] = float(score)
            hits.append(meta)
            if len(hits) >= top_k:
                break
        return hits


def _matches(
    meta: dict,
    source: str | None,
    category: str | None,
    location: str | None,
    property_type: str | None,
) -> bool:
    if source and meta.get("source") != source:
        return False
    if category and meta.get("category") != category:
        return False
    if property_type:
        haystack = (meta.get("property_type") or "").lower()
        if property_type.lower() not in haystack:
            return False
    if location:
        blob = " ".join(part for part in (meta.get("location"), meta.get("city")) if part).lower()
        if location.lower() not in blob:
            return False
    return True
