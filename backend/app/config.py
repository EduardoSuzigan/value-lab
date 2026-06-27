"""Configuração central.

Segredos SEMPRE via env / .env / Actions Secrets — nunca no código.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Banco (Neon na produção; SQLite local para boot/desenvolvimento)
    database_url: str = "sqlite:///./value_lab.db"

    # Integrações externas (preenchidas via secret; vazias por padrão)
    odds_api_key: str = ""

    # Proteção da rota leve de refresh disparada por scheduler externo
    cron_secret: str = ""

    # Modelagem
    kelly_fraction: float = 0.25  # Kelly fracionado (default 25%); NUNCA Kelly cheio.


settings = Settings()
