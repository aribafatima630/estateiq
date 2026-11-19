from __future__ import annotations

import logging

import numpy as np

from app.core.config import Settings
from app.database.repository import Repository
from app.rag.chunking import chunks_for_record
from app.rag.index import Embedder, VectorIndex

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, settings: Settings, repository: Repository, embedder: Embedder, index: VectorIndex):
        self.settings = settings
        self.repository = repository
        self.embedder = embedder
        self.index = index

    def rebuild(self) -> int:
        records = self.repository.all_records()
        chunks = []
        for record in records:
            chunks.extend(chunks_for_record(record))
        if not chunks:
            self.index.build(np.zeros((0, 0), dtype="float32"), [])
            self.index.save(self.settings.index_path, self.settings.index_meta_path)
            return 0
        vectors = self.embedder.embed([chunk["text"] for chunk in chunks])
        self.index.build(vectors, chunks)
        self.index.save(self.settings.index_path, self.settings.index_meta_path)
        logger.info("Indexed %s chunks from %s records", len(chunks), len(records))
        return len(chunks)

    def load(self) -> bool:
        return self.index.load(self.settings.index_path, self.settings.index_meta_path)

    def search(
        self,
        query: str,
        *,
        source: str | None = None,
        category: str | None = None,
        location: str | None = None,
        property_type: str | None = None,
    ) -> list[dict]:
        if not query.strip() or not self.index.ready:
            return []
        vector = self.embedder.embed([query])[0]
        hits = self.index.search(
            vector,
            top_k=self.settings.retrieval_top_k,
            threshold=self.settings.retrieval_threshold,
            source=source,
            category=category,
            location=location,
            property_type=property_type,
        )
        return hits
