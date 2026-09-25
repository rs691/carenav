import asyncio
import os
import re

# Don't let stale shell env override .env for this smoke test
for k in list(os.environ):
    if k.startswith("SUPABASE") or k in ("DATABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"):
        # only clear if we want file-based — actually keep and print
        pass

from core.settings import settings

print("supabase_url", settings.supabase_url)
print("project_ref", settings.project_ref)
dsn = settings.asyncpg_dsn
print("dsn", re.sub(r":([^:@/]+)@", ":***@", dsn))


async def main() -> None:
    import asyncpg

    try:
        conn = await asyncpg.connect(
            dsn, ssl="require", timeout=20, statement_cache_size=0
        )
        n = await conn.fetchval("select count(*) from sessions")
        await conn.execute(
            """
            insert into sessions (id, tenant_id, member_id)
            values ('test_sess_smoke', 'tenant_bcbs', 'member_smoke')
            on conflict (id) do update set updated_at = now()
            """
        )
        await conn.execute(
            """
            insert into turns (session_id, tenant_id, role, content)
            values ('test_sess_smoke', 'tenant_bcbs', 'user', 'smoke test')
            """
        )
        turns = await conn.fetchval(
            "select count(*) from turns where session_id='test_sess_smoke'"
        )
        await conn.execute("delete from turns where session_id='test_sess_smoke'")
        await conn.execute("delete from sessions where id='test_sess_smoke'")
        await conn.close()
        print("DB_OK sessions=", n, "turn_write_ok=", turns)
    except Exception as e:
        print("DB_FAIL", type(e).__name__, e)


if __name__ == "__main__":
    asyncio.run(main())
