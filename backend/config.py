"""Environment-driven settings for the Ganglia server."""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-20b"


class Settings(BaseSettings):
    """Runtime settings. Secrets stay in the environment, never in git."""

    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    env: str = "development"
    database_url: str = f"sqlite:///{(DATA_DIR / 'ganglia.db').as_posix()}"
    secret_key: str = "dev-change-me"
    admin_token: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    walletconnect_project_id: str = ""
    llm_base_url: str = GROQ_BASE
    llm_model: str = GROQ_MODEL
    llm_json_mode: bool = True
    autonomous_seconds: int = 60
    scenario_cooldown_seconds: int = 45
    max_scenario_len: int = 280
    autonomous_enabled: bool = True
    allow_software_writer: bool = True
    tts_enabled: bool = True
    tts_voice: str = "en-US-JennyNeural"
    host_origin: str = "http://127.0.0.1:8080"

    @model_validator(mode="after")
    def _free_groq_defaults(self) -> "Settings":
        """Use Groq when the key is a Groq key, or when only GROQ_API_KEY is set."""

        groq = self.groq_api_key.strip()
        openai = self.openai_api_key.strip()
        if not openai and groq:
            self.openai_api_key = groq
            openai = groq
        if openai.startswith("gsk_"):
            if "openai.com" in self.llm_base_url:
                self.llm_base_url = GROQ_BASE
            if self.llm_model.startswith("gpt-"):
                self.llm_model = GROQ_MODEL
        return self


def get_settings() -> Settings:
    """Load settings once per process from env / .env."""

    return Settings()
