"""Application configuration (env-driven, no secrets committed)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    All values can be overridden via environment variables or a .env file
    (see .env.example at the repository root).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- FalkorDB ---
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_username: str = ""  # optional ACL auth
    falkordb_password: str = ""
    graph_name: str = "sentinelgraph"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Investigation engine ---
    # Maximum traversal depth when correlating alerts (bounded multi-hop).
    max_traversal_hops: int = 4
    # Minimum score for an alert to be grouped with the seed alert.
    correlation_threshold: float = 3.0
    # Minimum similarity score to link a new incident to a historical one.
    memory_similarity_threshold: float = 0.2

    # --- Optional LLM (core pipeline works without it) ---
    llm_provider: str = ""  # e.g. "openai"; empty disables LLM summarization
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # --- Demo ---
    # Seed the demo dataset on startup when the graph is empty.
    auto_seed_on_startup: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
