"""Env flags for the Mongo → Supabase fold. No FastAPI, no live DB."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import env_config as ec


@pytest.fixture(autouse=True)
def clean_db_env(monkeypatch):
    for key in (
        "MONGO_URL",
        "DB_NAME",
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_missing_mongo_does_not_look_configured():
    runtime = ec.load_runtime_env()
    assert runtime.mongo_configured is False
    assert ec.mongo_connect_args() is None
    payload = runtime.health()
    assert payload["ok"] is True
    assert payload["storage"]["mongodb_configured"] is False
    assert payload["storage"]["supabase_used_by_api"] is False
    assert payload["storage"]["active"] == "none"


def test_mongo_needs_both_url_and_db_name(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    assert ec.load_runtime_env().mongo_configured is False
    monkeypatch.setenv("DB_NAME", "subsidekick")
    assert ec.load_runtime_env().mongo_configured is True
    assert ec.mongo_connect_args() == ("mongodb://127.0.0.1:27017", "subsidekick")


def test_supabase_env_is_presence_only_and_unused(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://vbcyzvlyfzapnifqrwlf.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "not-a-real-key")
    runtime = ec.load_runtime_env()
    assert runtime.supabase_env_present is True
    health = runtime.health()
    assert health["storage"]["supabase_env_present"] is True
    assert health["storage"]["supabase_used_by_api"] is False
    assert "not-a-real-key" not in str(health)
    assert "vbcyzvlyfzapnifqrwlf" not in str(health)
