"""Backend configuration for Borb.

All runtime configuration is loaded here from environment variables (prefixed
with ``BORB_``) and/or a ``.env`` file. The most important value is
``authority_mode``.

Design rule: ``authority_mode`` is a *backend start mode*. It is part of the
runtime configuration of the backend and must NOT be settable through a prompt.
A user prompt like "activate authority mode" must never change it. The model may
only *detect* in which mode the backend is already running. To enforce this, the
loaded :class:`Settings` object is treated as immutable for the lifetime of the
process.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthorityMode(str, Enum):
    """Backend authority mode.

    * ``normal``    -> a Policy Engine evaluates every planned action.
    * ``authority`` -> full execution authority (local dev/testing only).
    """

    NORMAL = "normal"
    AUTHORITY = "authority"


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"  # OpenAI-compatible (OpenAI, vLLM, LM Studio, ...)


class WebsearchProvider(str, Enum):
    DUCKDUCKGO = "duckduckgo"  # no API key required (via the ``ddgs`` package)


class Settings(BaseSettings):
    """Immutable backend configuration, sourced from env / ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="BORB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,  # configuration is read-only at runtime
    )

    # --- environment / authority ---
    env: str = "development"
    authority_mode: AuthorityMode = AuthorityMode.NORMAL

    # --- capability switches / workspace ---
    workspace_root: str = "."
    allow_shell: bool = True
    allow_filesystem: bool = True
    allow_network: bool = True
    allow_process_control: bool = False
    allow_package_install: bool = False
    allow_sudo: bool = False
    allow_websearch: bool = True

    # --- audit ---
    audit_log: bool = True
    audit_log_file: Optional[str] = None

    # --- LLM ---
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    llm_model: str = "llama3.1"
    llm_temperature: float = 0.2
    llm_timeout: int = 120

    ollama_base_url: str = "http://localhost:11434"

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: Optional[str] = None

    # --- websearch ---
    websearch_provider: WebsearchProvider = WebsearchProvider.DUCKDUCKGO
    websearch_max_results: int = Field(default=5, ge=1, le=25)
    websearch_timeout: int = 20

    # --- agent loop ---
    agent_max_steps: int = Field(default=6, ge=1, le=50)
    shell_timeout: int = 120

    # --- diary ---
    # Borb keeps a daily diary. At ``diary_time`` (local server time) he reflects
    # on the day; the backend persists the entry as
    # ``YYYYMMDD_Borb_Diary_Entry.md`` in ``diary_dir`` and then clears the live
    # conversation context so the next day starts fresh.
    diary_enabled: bool = True
    diary_time: str = "21:00"  # HH:MM, 24h, local server time
    diary_dir: str = "~/Borb_Diary"

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def is_authority(self) -> bool:
        return self.authority_mode == AuthorityMode.AUTHORITY


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so the configuration is loaded exactly once at startup and stays
    constant for the lifetime of the process.
    """

    return Settings()
