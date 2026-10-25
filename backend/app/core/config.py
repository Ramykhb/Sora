from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    api_key: SecretStr = SecretStr("local-development-only")
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:3000"]
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/visual_assistant"
    auto_migrate: bool = False
    storage_backend: str = "s3"
    local_storage_dir: Path = BACKEND_ROOT / "data" / "objects"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "frames"
    s3_access_key: SecretStr = SecretStr("rustfsadmin")
    s3_secret_key: SecretStr = SecretStr("rustfsadmin")
    frame_retention_hours: int = Field(default=24, ge=1, le=168)
    cleanup_interval_seconds: int = Field(default=60, ge=1)
    max_upload_mb: int = Field(default=15, ge=1, le=100)
    max_image_pixels: int = Field(default=20_000_000, ge=1000)
    max_image_side: int = Field(default=1280, ge=320, le=4096)
    min_sharpness: float = 20.0
    min_brightness: float = 5.0
    duplicate_hash_distance: int = Field(default=5, ge=0, le=64)
    sample_interval_seconds: float = Field(default=2.0, ge=0.25)
    recent_evidence_seconds: int = Field(default=15, ge=1)
    retrieval_top_k: int = Field(default=3, ge=1, le=6)
    ollama_url: str = "http://localhost:11434"
    vision_model: str = "qwen2.5vl:3b"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: Literal[1024] = 1024
    model_timeout_seconds: int = 120
    yolo_model: str = "yolo11n.pt"
    yolo_confidence: float = Field(default=0.35, ge=0, le=1)
    model_device: str = "cpu"
    whisper_model: str = "base"
    whisper_compute_type: str = "int8"
    max_audio_seconds: int = Field(default=60, ge=1, le=120)
    ocr_languages: str = "eng+fra+ara"
    espeak_binary: str = "espeak-ng"
    alert_cooldown_seconds: int = 30
    ice_servers: list[dict] = []
    max_live_sessions: int = Field(default=4, ge=1, le=32)
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")


settings = Settings()
