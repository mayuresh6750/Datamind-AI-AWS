from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:3000"

    # Supabase (Legacy / Optional)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Database
    database_url: str = ""
    aws_db_secret_name: str = "rds!db-45b6f72c-4a03-469c-ab9d-f374da4f1e34"
    aws_db_host: str = "database-1.crimi0cgox0o.eu-north-1.rds.amazonaws.com"
    aws_db_port: int = 5432
    aws_db_name: str = "postgres"
    aws_db_region: str = "eu-north-1"

    # Storage buckets
    storage_archive_bucket: str = "datamind-archive"
    storage_json_bucket: str = "datamind-json"

    # AWS Configuration
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = "datamind-ai-storage-dev-2026"
    aws_bedrock_region: str = "us-east-1"
    aws_bedrock_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    # LLM
    llm_provider: str = "aws_bedrock"
    llm_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    llm_api_key: str = ""

    # Embeddings
    embedding_provider: str = "aws_bedrock"
    aws_titan_embedding_model: str = "amazon.titan-embed-text-v2:0"
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
