import logging
import os

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
    """Validate security configuration and fail hard in production if insecure settings detected."""
    if settings.environment != "production":
        logger.info("Security validation skipped (non-production environment)")
        return

    errors: list[str] = []

    if settings.jwt_secret_key in INSECURE_JWT_SECRETS:
        errors.append(
            "HF_CDSS_JWT_SECRET_KEY is using a known insecure default in production environment. "
            "Set a strong, unique secret via HF_CDSS_JWT_SECRET_KEY environment variable."
        )

    if not settings.jwt_cookie_secure:
        errors.append(
            "HF_CDSS_JWT_COOKIE_SECURE is False in production. "
            "Cookies should be set with Secure flag to prevent interception. "
            "Set HF_CDSS_JWT_COOKIE_SECURE=true."
        )

    if settings.auth_login_enabled and not settings.auth_seed_users_json.strip():
        logger.warning(
            "Production login is enabled without HF_CDSS_AUTH_SEED_USERS_JSON; "
            "ensure users are provisioned securely and default seed file is not relied upon"
        )

    if settings.api_keys.strip() in {"", "change-me"}:
        logger.warning("HF_CDSS_API_KEYS is using a placeholder value in production environment")

    if errors:
        for error in errors:
            logger.error("SECURITY VALIDATION FAILED: %s", error)
        logger.critical(
            "Application startup aborted due to %d security error(s) in production. "
            "Fix the issues above before deploying.",
            len(errors),
        )
        os._exit(1)  # noqa: PLW6091


def check_security_startup() -> None:
    """Alias for validate_security_configuration() for backward compatibility."""
    validate_security_configuration()
