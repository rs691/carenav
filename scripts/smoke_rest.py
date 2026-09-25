"""Smoke-test Supabase REST persistence (service role)."""
import asyncio
import uuid

from core.session import load_session, save_turn, Turn, get_session_summary
from core.settings import settings


async def main() -> None:
    print("supabase_url", settings.supabase_url)
    print("service_role_set", bool(settings.service_role_key))
    print("jwks", settings.jwks_url)

    sid = f"smoke_{uuid.uuid4()}"
    session = await load_session(sid, "tenant_bcbs", "member_smoke")
    print("loaded", session.turn_count, "persistence check next")

    await save_turn(sid, "tenant_bcbs", Turn(role="user", content="hello from smoke"))
    await save_turn(
        sid,
        "tenant_bcbs",
        Turn(role="assistant", content="hi", agent_id="benefits", intent="benefits_lookup"),
    )

    again = await load_session(sid, "tenant_bcbs", "member_smoke")
    summary = await get_session_summary(sid, "tenant_bcbs")
    print("turns_after", again.turn_count, "summary", summary)

    if again.turn_count >= 2:
        print("REST_OK")
    else:
        print("REST_FAIL unexpected turn count")


if __name__ == "__main__":
    asyncio.run(main())
