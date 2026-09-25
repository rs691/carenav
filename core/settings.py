from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def normalize_asyncpg_dsn(database_url: str) -> str:
    """Normalize DATABASE_URL for asyncpg (strip quotes, SQLAlchemy scheme)."""
    raw = database_url.strip().strip('"').strip("'")
    if not raw:
        return ""
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw.removeprefix("postgresql+asyncpg://")
    elif raw.startswith("postgres://"):
        raw = "postgresql://" + raw.removeprefix("postgres://")
    return raw


def project_ref_from_database_url(database_url: str) -> str:
    """Extract project ref from db.<ref>.supabase.co or postgres.<ref>@pooler."""
    dsn = normalize_asyncpg_dsn(database_url)
    if not dsn:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        host = parsed.hostname or ""
        user = parsed.username or ""
        if host.startswith("db.") and host.endswith(".supabase.co"):
            return host.split(".")[1]
        if user.startswith("postgres.") and "pooler.supabase.com" in host:
            return user.removeprefix("postgres.")
    except Exception:
        return ""
    return ""


def rewrite_supabase_pooler_dsn(dsn: str, project_ref: str, region: str = "us-east-1") -> str:
    """Prefer Supavisor pooler host (IPv4) over db.<ref>.supabase.co (often IPv6-only)."""
    if not dsn or "supabase.co" not in dsn:
        return dsn
    if "pooler.supabase.com" in dsn:
        return dsn
    if not project_ref:
        return dsn

    try:
        from urllib.parse import quote, urlparse, urlunparse

        parsed = urlparse(dsn)
        password = parsed.password or ""
        user = f"postgres.{project_ref}"
        host = f"aws-0-{region}.pooler.supabase.com"
        netloc = f"{user}:{quote(password, safe='')}@{host}:6543"
        return urlunparse(("postgresql", netloc, parsed.path or "/postgres", "", parsed.query, ""))
    except Exception:
        return dsn


class Settings(BaseSettings):
    # Prefer project .env over machine/user environment variables.
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    # Vector DB
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")

    # Database / Supabase
    database_url: str = Field(default="", alias="DATABASE_URL")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_key: str = Field(default="", alias="SUPABASE_SERVICE_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    supabase_jwks_url: str = Field(default="", alias="SUPABASE_JWKS_URL")
    supabase_db_region: str = Field(default="us-east-1", alias="SUPABASE_DB_REGION")
    supabase_use_pooler: bool = Field(default=True, alias="SUPABASE_USE_POOLER")

    # Auth
    jwt_secret: str = Field(default="dev-secret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=480, alias="JWT_EXPIRE_MINUTES")
    cors_origins: str = Field(
        default="http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator(
        "database_url",
        "supabase_url",
        "supabase_service_key",
        "supabase_service_role_key",
        "supabase_jwt_secret",
        "supabase_jwks_url",
        "qdrant_url",
        "qdrant_api_key",
        "cors_origins",
        mode="before",
    )
    @classmethod
    def strip_quotes(cls, v):
        if isinstance(v, str):
            return v.strip().strip('"').strip("'")
        return v

    @property
    def service_role_key(self) -> str:
        return self.supabase_service_role_key or self.supabase_service_key

    @property
    def project_ref(self) -> str:
        from_db = project_ref_from_database_url(self.database_url)
        if from_db:
            return from_db
        url = self.supabase_url
        if "://" in url:
            host = url.split("://", 1)[1].split("/", 1)[0]
            return host.split(".")[0]
        return ""

    @property
    def asyncpg_dsn(self) -> str:
        dsn = normalize_asyncpg_dsn(self.database_url)
        if self.supabase_use_pooler and self.project_ref:
            dsn = rewrite_supabase_pooler_dsn(dsn, self.project_ref, self.supabase_db_region)
        return dsn

    @property
    def persistence_enabled(self) -> bool:
        return bool(self.asyncpg_dsn)

    @property
    def jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url.rstrip("/")
        if self.project_ref:
            return f"https://{self.project_ref}.supabase.co/auth/v1/.well-known/jwks.json"
        base = self.supabase_url.rstrip("/")
        if not base:
            return ""
        return f"{base}/auth/v1/.well-known/jwks.json"


settings = Settings()
