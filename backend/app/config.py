"""Application configuration."""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """App settings from env or .env file."""
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/oncall.db"
    
    # ChromaDB persistence
    chroma_persist_dir: str = "./data/chroma_db"
    
    # OpenAI (ChatGPT): used for embeddings + LLM answers when set
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # for chat/completions (search answer)
    openai_embedding_model: str = "text-embedding-3-small"  # for vector search
    # Set True to verify SSL; set False for corporate proxy (avoids CERTIFICATE_VERIFY_FAILED)
    openai_ssl_verify: bool = False
    
    # Fallback: only if openai_api_key is empty (Hugging Face / sentence-transformers)
    embedding_model: str = "all-MiniLM-L6-v2"
    hf_token: str = ""
    
    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k_retrieve: int = 5
    # Retrieve more candidates then re-rank by query-term match to reduce irrelevant results
    search_candidates_multiplier: int = 3
    # Max chars per chunk in search response (reduces payload and UI clutter)
    chunk_preview_chars: int = 350
    # Search cache: in-process LRU by default. Set redis_url to share cache across workers/replicas.
    enable_search_cache: bool = True
    search_cache_max_entries: int = 256  # LRU cap when using in-memory backend
    redis_url: str = ""  # e.g. redis://localhost:6379/0 — empty means in-memory only
    search_cache_ttl_seconds: int = 86400  # Redis key TTL (orphaned keys after version bump)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure data dirs exist
Path("./data").mkdir(exist_ok=True)
Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
