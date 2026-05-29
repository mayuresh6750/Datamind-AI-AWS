from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:3000"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Database
    database_url: str

    # Storage buckets
    storage_archive_bucket: str = "datamind-archive"
    storage_json_bucket: str = "datamind-json"

    # LLM
    llm_provider: str = "google_gemini"
    llm_model: str = "gemini-2.0-flash"
    llm_api_key: str = ""

    # Embeddings
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_device: str = "cpu"

    # Rate limiting
    rate_limit_per_minute: int = 100
    max_concurrent_pipelines: int = 5

    # LLM token budget per pipeline
    llm_max_input_tokens: int = 150_000
    llm_max_output_tokens: int = 25_000
    llm_cost_ceiling_usd: float = 0.30

    # Logging
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()  # type: ignore[call-arg]
