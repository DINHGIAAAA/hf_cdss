import logging

from app.core.config import settings


logger = logging.getLogger(__name__)

INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change-me-in-production",
        "change-me",
        "hf-cdss-dev-jwt-secret-change-me",
    }
)


def validate_security_configuration() -> None:
    if settings.environment != "production":
        return

    if settings.jwt_secret_key in INSECURE_JWT_SECRETS:
        logger.error(
            "HF_CDSS_JWT_SECRET_KEY is using a known insecure default in production environment"
        )

    if settings.auth_login_enabled and not settings.auth_seed_users_json.strip():
        logger.warning(
            "Production login is enabled without HF_CDSS_AUTH_SEED_USERS_JSON; "
            "ensure users are provisioned securely and default seed file is not relied upon"
        )

    if settings.api_keys.strip() in {"", "change-me"}:
        logger.warning("HF_CDSS_API_KEYS is using a placeholder value in production environment")
