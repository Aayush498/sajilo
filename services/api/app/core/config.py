"""Application settings, loaded once from the environment."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application --------------------------------------------------------
    ENVIRONMENT: Literal["dev", "test", "staging", "production"] = "dev"
    DEBUG: bool = True
    PROJECT_NAME: str = "Sajilo"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    # NoDecode: the env value is a comma-separated string, not JSON. Without it
    # pydantic-settings tries to json.loads() the raw value before validation.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Security -----------------------------------------------------------
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    ADMIN_REFRESH_TOKEN_TTL_HOURS: int = 12

    # --- Database -----------------------------------------------------------
    POSTGRES_USER: str = "sajilo"
    POSTGRES_PASSWORD: str = "sajilo_dev_password"
    POSTGRES_DB: str = "sajilo"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- Redis --------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- OTP ----------------------------------------------------------------
    OTP_LENGTH: int = 6
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_PER_PHONE_PER_DAY: int = 10
    # "console" prints the code to the logs. Real providers land in Module 5+.
    SMS_PROVIDER: Literal["console"] = "console"
    # Fixed codes for QA / app-store reviewers: "+9779800000000:123456,..."
    OTP_TEST_NUMBERS: str = ""

    RATE_LIMIT_ENABLED: bool = True

    # --- Bootstrap admin ----------------------------------------------------
    SEED_ADMIN_PHONE: str = "+9779800000001"
    SEED_ADMIN_EMAIL: str = "admin@sajilo.com.np"
    SEED_ADMIN_PASSWORD: str = "ChangeMeNow123!"
    SEED_ADMIN_NAME: str = "Sajilo Admin"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def otp_test_numbers(self) -> dict[str, str]:
        """Phone -> fixed OTP. Ignored in production."""
        if self.is_production or not self.OTP_TEST_NUMBERS:
            return {}
        pairs = (item.split(":", 1) for item in self.OTP_TEST_NUMBERS.split(",") if ":" in item)
        return {phone.strip(): code.strip() for phone, code in pairs}


@lru_cache
def get_settings() -> Settings:
    """Load settings, refusing to boot production with development defaults.

    Each of these fails loudly at startup rather than at 3am. A wrong CORS
    origin in particular does not error anywhere — the API answers normally and
    the browser silently discards every response, which looks like the frontend
    being broken.
    """
    settings = Settings()
    if not settings.is_production:
        return settings

    problems: list[str] = []
    if settings.SECRET_KEY.startswith("dev-only"):
        problems.append("SECRET_KEY is still the development default.")
    if any("localhost" in o or "127.0.0.1" in o for o in settings.CORS_ORIGINS):
        problems.append(
            f"CORS_ORIGINS still points at localhost ({', '.join(settings.CORS_ORIGINS)}). "
            "Set it to the real site origin, or browsers will drop every response."
        )
    if settings.DEBUG:
        problems.append("DEBUG is true.")
    if settings.SEED_ADMIN_PASSWORD == "ChangeMeNow123!":
        problems.append("SEED_ADMIN_PASSWORD is still the documented default.")

    if problems:
        detail = "\n  - ".join(problems)
        raise RuntimeError(f"Refusing to start in production:\n  - {detail}")
    return settings


settings = get_settings()
