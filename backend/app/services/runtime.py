from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.database.db import Database
from app.database.repository import Repository
from app.rag.index import SentenceTransformerEmbedder, VectorIndex
from app.rag.retrieval import RetrievalService
from app.services.chat import ChatService
from app.services.jobs import JobRunner
from app.services.llm import OpenRouterClient


@dataclass
class Runtime:
    settings: Settings
    repository: Repository
    retrieval: RetrievalService
    llm: OpenRouterClient
    chat: ChatService
    jobs: JobRunner


def build_runtime(
    settings: Settings | None = None,
    embedder=None,
    llm: OpenRouterClient | None = None,
) -> Runtime:
    settings = settings or get_settings()
    settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    repository = Repository(Database(settings.database_path))
    embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model)
    retrieval = RetrievalService(settings, repository, embedder, VectorIndex())
    retrieval.load()
    if not retrieval.index.ready and settings.auto_index_on_start and repository.counts()["records"]:
        retrieval.rebuild()
    llm = llm or OpenRouterClient(settings)
    return Runtime(
        settings=settings,
        repository=repository,
        retrieval=retrieval,
        llm=llm,
        chat=ChatService(repository, retrieval, llm),
        jobs=JobRunner(),
    )
