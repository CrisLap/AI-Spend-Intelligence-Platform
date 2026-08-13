from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Spend Intelligence Platform"
    environment: str = "development"
    debug: bool = True

    database_url: str = "postgresql://spenduser:spendpass@localhost:5432/spendintel"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "spend_documents"
    qdrant_contract_collection: str = "spend_contracts"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    ollama_host: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: int = 30

    groq_api_key: str | None = None
    groq_chat_model: str = "openai/gpt-oss-20b"
    groq_timeout: int = 30

    jina_api_key: str | None = None
    jina_embed_model: str = "jina-embeddings-v3"
    jina_timeout: int = 30

    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 50

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    anomaly_zscore_threshold: float = 2.5
    duplicate_similarity_threshold: float = 0.88

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

