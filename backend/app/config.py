import urllib.parse
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate .env file relative to this file: backend/.env
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def build_default_sqlserver_url() -> str:
    """Builds default Microsoft SQL Server 2022 Express connection URL with Windows Authentication."""
    raw_odbc = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        r"SERVER=.\SQLEXPRESS;"
        "DATABASE=StudentSkillGapAnalyzer;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(raw_odbc)}"


class Settings(BaseSettings):
    """
    Application configuration settings loaded from environment variables and .env file.
    Default database engine is Microsoft SQL Server 2022 (ODBC Driver 17 for SQL Server).
    """
    app_name: str = Field(default="Student Skill Gap Analyzer", validation_alias="APP_NAME")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default_factory=build_default_sqlserver_url,
        validation_alias="DATABASE_URL",
    )
    # Granular SQL Server configuration (used if DATABASE_URL is not explicitly specified)
    db_server: str = Field(default=r".\SQLEXPRESS", validation_alias="DB_SERVER")
    db_name: str = Field(default="StudentSkillGapAnalyzer", validation_alias="DB_NAME")
    db_driver: str = Field(default="ODBC Driver 17 for SQL Server", validation_alias="DB_DRIVER")
    db_trusted_connection: bool = Field(default=True, validation_alias="DB_TRUSTED_CONNECTION")
    db_user: str | None = Field(default=None, validation_alias="DB_USER")
    db_password: str | None = Field(default=None, validation_alias="DB_PASSWORD")

    jwt_secret: str = Field(
        default="dev_secret_key_student_skill_gap_analyzer_only",
        validation_alias="JWT_SECRET",
    )
    access_token_expire_minutes: int = Field(
        default=10080,  # 7 days (10080 minutes) to ensure persistent student sessions across visits
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    frontend_origin: str = Field(
        default="http://localhost:5173",
        validation_alias="FRONTEND_ORIGIN",
    )
    job_freshness_days: int = Field(
        default=30,
        validation_alias="JOB_FRESHNESS_DAYS",
        description="Threshold in days after which a posting is flagged as stale",
    )
    # Optional SMTP configuration for email delivery
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, validation_alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(
        default="noreply@skillgap.analyzer",
        validation_alias="SMTP_FROM_EMAIL",
    )

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        # 1. If raw ODBC string passed (e.g. "DRIVER={...};SERVER=..."):
        if "DRIVER=" in v.upper() and not v.startswith("mssql"):
            return f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(v)}"

        # 2. Normalize Render/Heroku postgres:// URLs to postgresql://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)

        # 3. Fix relative SQLite paths to always point to BASE_DIR / app.db
        if v.startswith("sqlite:///") and not v.startswith("sqlite:////") and ":memory:" not in v:
            relative_path = v.replace("sqlite:///", "")
            if relative_path.startswith("./") or not Path(relative_path).is_absolute():
                clean_rel = relative_path.lstrip("./")
                abs_db_path = (BASE_DIR / clean_rel).resolve()
                v = f"sqlite:///{abs_db_path.as_posix()}"

        return v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


settings = Settings()
