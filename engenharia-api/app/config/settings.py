"""Configurações centrais da aplicação (variáveis de ambiente com prefixo API_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore")

    # Aplicação
    app_name: str = "Engenharia API"
    version: str = "1.0.0"
    debug: bool = False

    # Upload
    max_upload_size_mb: int = 25
    allowed_extensions: list[str] = ["pdf", "png", "jpg", "jpeg", "tiff", "tif"]
    allowed_mime_types: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
    ]

    # Segurança
    cors_origins: list[str] = ["*"]  # em produção: ["https://seuusuario.github.io"]
    rate_limit: str = "30/minute"
    jwt_enabled: bool = False
    jwt_secret: str = "troque-este-segredo-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # Cache
    cache_ttl_seconds: int = 3600
    cache_max_items: int = 128

    # OCR
    # "tesseract": usa apenas Tesseract (leve; recomendado em planos com pouca RAM,
    #   como o Free do Render, onde EasyOCR/torch podem estourar a memória e derrubar o processo).
    # "easyocr": usa apenas EasyOCR (mais preciso, requer bem mais memória/CPU).
    # "auto": tenta EasyOCR e usa Tesseract como fallback caso EasyOCR falhe.
    ocr_engine: str = "tesseract"
    ocr_languages: list[str] = ["pt", "en"]
    ocr_min_confidence: float = 0.35

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
