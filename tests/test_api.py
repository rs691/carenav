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
    llm_provider="openai",
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
        patch("core.llm.settings", settings_mod.settings),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chat", json=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_used"] == "benefits"
    assert data["intent"] == "benefits_lookup"
    assert data["reply"]
    assert data["turn_count"] >= 2


def _token(
    app_metadata: dict | None = None,
    user_metadata: dict | None = None,
    sub: str = "user-123",
) -> str:
    from jose import jwt

    return jwt.encode(
        {
            "sub": sub,
            "email": "jordan@example.com",
            "aud": "authenticated",
            "app_metadata": app_metadata or {},
            "user_metadata": user_metadata or {},
        },
        "test",
        algorithm="HS256",
    )


async def _post_chat(token: str, message: str = "What is my deductible?"):
    transport = ASGITransport(app=app)
    with (
        patch("middleware.auth.settings", settings_mod.settings),
        patch("core.llm.settings", settings_mod.settings),
        patch("rag.retriever.retrieve", new=AsyncMock(return_value=[])),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={"session_id": "sess_identity", "message": message},
                headers={"Authorization": f"Bearer {token}"},
            )


@pytest.mark.asyncio
async def test_unlinked_user_gets_general_agent():
    resp = await _post_chat(_token(user_metadata={"full_name": "Jordan Rivera"}))
    assert resp.status_code == 200
    assert resp.json()["agent_used"] == "general"


@pytest.mark.asyncio
async def test_user_metadata_tenant_is_not_trusted():
    resp = await _post_chat(_token(user_metadata={"tenant_id": "tenant_bcbs"}))
    assert resp.status_code == 200
    assert resp.json()["agent_used"] == "general"


@pytest.mark.asyncio
async def test_unlinked_user_can_still_escalate():
    resp = await _post_chat(_token(), "I need to speak with a human representative")
    assert resp.json()["agent_used"] == "escalation"


@pytest.mark.asyncio
async def test_me_reports_link_and_name():
    transport = ASGITransport(app=app)
    token = _token(
        app_metadata={"tenant_id": "tenant_bcbs", "onboarded": True},
        user_metadata={"full_name": "Jordan Rivera"},
    )
    with patch("middleware.auth.settings", settings_mod.settings):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["linked"] is True
    assert data["onboarded"] is True
    assert data["plan_name"] == "BlueCross Premier PPO"
    assert data["first_name"] == "Jordan"


@pytest.mark.asyncio
async def test_other_member_cannot_use_someone_elses_session():
    first = await _post_chat(_token(sub="member-a"), "What is a deductible?")
    assert first.status_code == 200
    second = await _post_chat(_token(sub="member-b"), "What did I ask before?")
    assert second.status_code == 403
    assert session_mod._memory_sessions["sess_identity"].member_id == "member-a"


@pytest.mark.asyncio
async def test_history_survives_linking_a_plan():
    await _post_chat(_token(sub="member-a"), "What is a deductible?")
    linked = _token(sub="member-a", app_metadata={"tenant_id": "tenant_bcbs", "onboarded": True})
    resp = await _post_chat(linked, "Is my MRI covered?")
    assert resp.status_code == 200
    assert resp.json()["turn_count"] == 4


@pytest.mark.asyncio
async def test_me_requires_sign_in():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/me", headers={"x-tenant-id": "tenant_bcbs"})
    assert resp.status_code == 401
