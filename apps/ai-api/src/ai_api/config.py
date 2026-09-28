from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_API_", env_file=".env", extra="ignore")

    db_url: str = "postgresql://dramamemory:dramamemory@localhost:5432/dramamemory"
    db_pool_size: int = 5

    # Embedding model id as stored in search_document.embedding_model. Changing it
    # requires a migration for the vector dimension and a full re-embed.
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    # "bge" loads sentence-transformers; "fake" is a deterministic hash embedder for tests/CI.
    embedder: str = "bge"
    embed_batch_size: int = 16

    # Retrieval knobs (docs/RAG_DESIGN.md). Versioned so caches/evals can key on them.
    retrieval_version: str = "hybrid-v1"
    rrf_k: int = 60
    candidates_per_list: int = 50

    # Optional cross-encoder rerank of the fused top-N (RAG_DESIGN §8, DM-605).
    # "none" | "bge" (sentence-transformers CrossEncoder) | "fake" (tests). Applied only when a
    # request asks for it (rerank=true) so the default path stays cheap.
    reranker: str = "none"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_candidates: int = 30

    # Neo4j read model. Empty uri = graph features off (search still works without it).
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Shared secret for /internal/* (embedding refresh from Airflow). Empty = open (local only).
    internal_token: str = ""


@lru_cache
def settings() -> Settings:
    return Settings()
