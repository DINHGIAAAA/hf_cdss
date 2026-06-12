from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Heart Failure CDSS"
    version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"
    api_keys: str = ""
    api_key_header: str = "x-api-key"
    max_request_body_bytes: int = 1_000_000
    openai_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_type: str = "responses"
    llm_timeout_seconds: float = 20.0
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: int = 600
    llm_cache_max_entries: int = 128
    postgres_dsn: str = "postgresql://hf_cdss:hf_cdss@localhost:55432/hf_cdss"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "heart_failure_evidence"
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = "http://localhost:11434"
    embedding_dimensions: int = 384
    semantic_rerank_enabled: bool = True
    semantic_rerank_weight: float = 0.75
    semantic_rerank_candidates: int = 24
    datastore_bootstrap_on_startup: bool = False
    retrieval_backend: str = "local"
    artifact_storage: str = "local"
    artifact_cache_root: str | None = None
    s3_endpoint_url: str = "http://localhost:4566"
    raw_bucket: str = "hf-cdss-raw"
    processed_bucket: str = "hf-cdss-processed"
    s3_prefix: str = "heart_failure"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_default_region: str = "us-east-1"
    postgres_audit_enabled: bool = False
    audit_schema_version: str = "2026-06-12"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    verification_agent_mode: str = "rule_based"
    verification_agent_model: str | None = None
    verification_agent_max_iterations: int = 2
    verification_agent_max_tokens: int = 140
    verification_agent_timeout_seconds: float = 90.0
    verification_agent_workers: int = 2
    verification_agent_llm_agents: str = "evidence_agent,guideline_alignment_agent"
    verification_agent_tool_mode: str = "direct"
    verification_retrieval_top_k: int = 3
    verification_cache_enabled: bool = True
    verification_cache_ttl_seconds: int = 300
    verification_cache_max_entries: int = 128

    model_config = SettingsConfigDict(env_prefix="HF_CDSS_", env_file=".env", extra="ignore")


settings = Settings()
