from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8000
    self_url: str = "http://localhost:8000"
    gateway_url: str = "http://localhost:9100"
    travel_url: str = "http://localhost:9200"
    inventory_url: str = "http://localhost:9300"
    hospital_token: str = "hospital-token"
    coordinator_token: str = "coordinator-token"
    kit_path: str = "./participant_kit"
    database_url: str = "sqlite+aiosqlite:///./bloodnet.db"
    log_level: str = "INFO"

    clock_cache_ttl_sec: float = 0.5
    http_timeout_sec: float = 8.0
    http_max_retries: int = 3

    dispatcher_tick_sec: float = 1.0
    wave_max_size: int = 80
    wave_min_size: int = 24
    wave_size_factor: int = 6
    wave_interval_min: float = 45.0
    wave_max_count: int = 4
    reminder_interval_min: float = 30.0
    pending_policy: str = "burst_hold"
    suspicious_units_threshold: int = 15
    burst_window_min: float = 15.0
    burst_max_units: int = 30
    alloc_retry_interval_min: float = 20.0
    ranking_strategy: str = "travel_time"
    ai_model_path: str = "./app/ai/model/ranker.joblib"
    disable_outreach: bool = False


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings()
