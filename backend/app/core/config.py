from pydantic import AliasChoices, Field
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
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b"
    llm_api_type: str = "chat_completions"
    llm_timeout_seconds: float = 90.0
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: int = 600
    llm_cache_max_entries: int = 128
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_cookie_name: str = "hf_cdss_session"
    jwt_cookie_secure: bool = False
    jwt_cookie_samesite: str = "lax"
    auth_login_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("auth_login_enabled", "auth_dev_login_enabled"),
    )
    auth_seed_users_json: str = Field(
        default="",
        validation_alias=AliasChoices("auth_seed_users_json", "auth_dev_users_json"),
    )
    clinical_intake_llm_timeout_seconds: float = 90.0
    clinical_intake_llm_max_tokens: int = 700
    clinical_intake_semantic_enabled: bool = True
    clinical_intake_semantic_threshold: float = 0.52
    clinical_intake_history_enabled: bool = True
    clinical_intake_history_max_messages: int = 12
    clinical_intake_history_relevance_threshold: float = 0.38
    clinical_intake_selective_llm_enabled: bool = True
    clinical_intake_selective_min_confidence: float = 0.75
    clinical_intake_selective_simple_missing_max: int = 3
    clinical_intake_selective_complexity_word_threshold: int = 80
    postgres_dsn: str = "postgresql://hf_cdss:hf_cdss@localhost:55432/hf_cdss"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "heart_failure_evidence"
    embedding_provider: str = "ollama"
    embedding_model: str = "bge-m3"
    embedding_base_url: str = "http://localhost:11434"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 16
    semantic_rerank_enabled: bool = True
    semantic_rerank_weight: float = 0.75
    semantic_rerank_candidates: int = 24
    retrieval_backend: str = "local"
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
    auth_login_rate_limit_requests: int = 10
    auth_login_rate_limit_window_seconds: int = 60
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    verification_agent_mode: str = "hybrid"
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
    dose_calculator_enabled: bool = True
    dose_rules_cache_ttl_seconds: int = 300
    interaction_rules_cache_ttl_seconds: int = 300
    gdmt_policy_cache_ttl_seconds: int = 300
    dose_safety_warnings_cache_ttl_seconds: int = 300
    kg_dose_overlays_cache_ttl_seconds: int = 300
    hyde_retrieval_enabled: bool = True
    hyde_retrieval_model: str = "qwen2.5:1.5b"
    hyde_retrieval_timeout_seconds: float = 20.0
    hyde_retrieval_max_tokens: int = 220
    hyde_retrieval_cache_ttl_seconds: int = 600
    hyde_retrieval_cache_max_entries: int = 256
    hyde_retrieval_min_query_chars: int = 8
    hyde_retrieval_combine_baseline: bool = True

    model_config = SettingsConfigDict(env_prefix="HF_CDSS_", env_file=".env", extra="ignore")


settings = Settings()
