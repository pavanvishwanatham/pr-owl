from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""
    github_api_base: str = "https://github.fkinternal.com/api/v3"

    # AI
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    openai_api_base: str = ""  # leave empty to use OpenAI default

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/pr_agent"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    max_diff_size_kb: int = 500
    skip_ai_for_large_prs: bool = True
    large_pr_file_threshold: int = 50  # skip AI if PR changes more files than this


@lru_cache
def get_settings() -> Settings:
    return Settings()
