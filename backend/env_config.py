"""Process env for the FastAPI app.

Reads names only. Never returns secret values. Mongo is the live store today;
Supabase env is the fold target and is unused by routes until a later PR.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _stripped(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _present(*names: str) -> bool:
    return bool(_stripped(*names))


@dataclass(frozen=True)
class RuntimeEnv:
    mongo_configured: bool
    supabase_url_present: bool
    supabase_anon_present: bool
    supabase_service_present: bool

    @property
    def supabase_env_present(self) -> bool:
        return self.supabase_url_present and (
            self.supabase_anon_present or self.supabase_service_present
        )

    def health(self) -> dict:
        if self.mongo_configured:
            active = "mongodb"
        elif self.supabase_env_present:
            active = "none"  # env present, routes not wired
        else:
            active = "none"
        return {
            "service": "subsidekick",
            "ok": True,
            "storage": {
                "active": active,
                "mongodb_configured": self.mongo_configured,
                "supabase_env_present": self.supabase_env_present,
                "supabase_used_by_api": False,
            },
        }


def load_runtime_env() -> RuntimeEnv:
    mongo_url = _stripped("MONGO_URL")
    db_name = _stripped("DB_NAME")
    return RuntimeEnv(
        mongo_configured=bool(mongo_url and db_name),
        supabase_url_present=_present("SUPABASE_URL"),
        supabase_anon_present=_present(
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_ANON_KEY",
        ),
        supabase_service_present=_present(
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_SECRET_KEY",
        ),
    )


def mongo_connect_args() -> tuple[str, str] | None:
    """Return (url, db_name) when both are set; otherwise None (do not crash import)."""
    url = _stripped("MONGO_URL")
    name = _stripped("DB_NAME")
    if url and name:
        return url, name
    return None
