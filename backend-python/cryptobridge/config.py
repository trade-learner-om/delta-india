from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_LOG_DIR = REPO_ROOT / "logs"
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    mongodb_uri: str = Field(default="mongodb://localhost:27017/cryptobridge", validation_alias="MONGODB_URI")
    port: int = Field(default=8080, validation_alias="PORT")
    delta_api_base_url: str = Field(
        default="https://api.india.delta.exchange",
        validation_alias="DELTA_API_BASE_URL",
    )
    crypto_secret: str = Field(
        default="cryptobridge-dev-secret",
        validation_alias="CRYPTOBRIDGE_CRYPTO_SECRET",
    )
    delta_public_ws_url: str = Field(
        default="wss://public-socket.india.delta.exchange",
        validation_alias="DELTA_PUBLIC_WS_URL",
    )
    delta_private_ws_url: str = Field(
        default="wss://socket.india.delta.exchange",
        validation_alias="DELTA_PRIVATE_WS_URL",
    )
    cors_allow_origin_regex: str = Field(
        default=r"https?://([\w.-]+|\d{1,3}(\.\d{1,3}){3}|\[[:a-fA-F0-9:]+\])(:\d+)?",
        validation_alias="CORS_ALLOW_ORIGIN_REGEX",
    )
    cors_allowed_origins: str = Field(
        default="https://crypto.signalbridge.in,http://localhost:5173,http://127.0.0.1:5173,http://ec2-13-232-110-145.ap-south-1.compute.amazonaws.com:5173",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )
    public_api_base_url: str = Field(
        default="https://crypto.api.signalbridge.in",
        validation_alias="PUBLIC_API_BASE_URL",
    )
    server_public_ip: str = Field(
        default="",
        validation_alias="SERVER_PUBLIC_IP",
    )
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_to_file: bool = Field(default=True, validation_alias="LOG_TO_FILE")
    log_dir: str = Field(default=str(DEFAULT_LOG_DIR), validation_alias="LOG_DIR")
    log_file: str = Field(default="cryptobridge.log", validation_alias="LOG_FILE")
    log_max_bytes: int = Field(default=10_485_760, validation_alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(default=5, validation_alias="LOG_BACKUP_COUNT")
    user_agent: str = "CryptoBridge/0.1"
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
