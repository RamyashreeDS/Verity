from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nimble_api_key: str = ""
    liquid_url: str = ""
    liquid_ai_api_key: str = ""
    liquid_ai_model: str = "liquid-beacon-1.0"
    tinybird_api_key: str = ""
    tinybird_host: str = "https://api.tinybird.co"
    bfl_api_key: str = ""

    demo_mode: bool = False

    max_urls_per_query: int = 20
    max_concurrent_crawls: int = 5
    max_claim_age_hours: int = 48
    confidence_floor: float = 0.3
    confidence_floor_official: float = 0.2
    high_confidence_threshold: float = 0.7
    conflict_threshold: float = 0.2
    conflict_tolerance: float = 0.1
    staleness_window_hours: int = 6
    healing_confidence_floor: float = 0.6
    max_healing_retries: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
