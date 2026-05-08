from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    qcc_base_url: str = "https://www.qcc.com"
    qcc_login_url: str = "https://www.qcc.com/user_login"
    qcc_search_url: str = "https://www.qcc.com/web/search"
    storage_state_path: Path = Path("data/qcc_storage_state.json")
    user_data_dir: Path = Path("data/qcc_user_data")
    browser_headless: bool = True
    navigation_timeout_ms: int = 45000
    extraction_timeout_ms: int = 12000

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")


@lru_cache
def get_settings() -> Settings:
    return Settings()

