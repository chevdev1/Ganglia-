"""Pytest fixtures for the Ganglia API."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

os.environ.setdefault("AUTONOMOUS_ENABLED", "false")
os.environ["OPENAI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from backend.db import init_engine, reset_engine
from backend.main import app, mind, settings
from backend.services.writer import SoftwareWriter


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Yield an API client bound to an isolated SQLite database."""

    mind.settings.autonomous_enabled = False
    mind.settings.tts_enabled = False
    mind.settings.allow_software_writer = True
    mind.settings.openai_api_key = ""
    mind.writer = SoftwareWriter()
    settings.admin_token = "test-admin"
    settings.allow_software_writer = True
    settings.openai_api_key = ""
    settings.autonomous_enabled = False
    settings.tts_enabled = False
    reset_engine()
    url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    init_engine(url)
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()
