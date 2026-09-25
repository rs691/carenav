"""API smoke tests — no database or external services."""
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("APP_ENV", "development")

import core.session as session_mod
import core.settings as settings_mod

# Force offline settings (ignore machine/.env OpenAI + Supabase keys)
settings_mod.settings = settings_mod.Settings.model_construct(
    database_url="",
    supabase_url="",
    supabase_service_key="",
    supabase_service_role_key="",
    openai_api_key="",
    app_env="development",
    cors_origins="http://localhost:3000",
    jwt_secret="test",
    jwt_algorithm="HS256",
)

session_mod._rest_disabled = True
session_mod._force_memory = True
session_mod._memory_sessions.clear()

# Import app after settings override
from api import main as api_main

api_main.settings = settings_mod.settings
from api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clear_memory_sessions():
    session_mod._rest_disabled = True
    session_mod._force_memory = True
    session_mod._memory_sessions.clear()
    yield
    session_mod._memory_sessions.clear()


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_in_memory_session():
    transport = ASGITransport(app=app)
    headers = {"x-tenant-id": "tenant_bcbs"}
    body = {
        "member_id": "member_001",
        "session_id": "sess_api_test",
        "message": "What is my deductible?",
    }

    chunks = [
        {
            "text": "Individual deductible is $1,500.",
            "source_doc": "benefits.pdf",
            "section": "Cost share",
            "chunk_index": 0,
            "score": 0.9,
            "stale": False,
        }
    ]
    with (
        patch("rag.retriever.retrieve", new=AsyncMock(return_value=chunks)),
        patch("agents.benefits.retrieve", new=AsyncMock(return_value=chunks)),
        patch("agents.benefits.settings", settings_mod.settings),
        patch("orchestrator.classifier.settings", settings_mod.settings),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chat", json=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_used"] == "benefits"
    assert data["intent"] == "benefits_lookup"
    assert data["reply"]
    assert data["turn_count"] >= 2
