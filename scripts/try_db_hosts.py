"""Try several Supabase connection strategies and print which works."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlparse

from core.settings import settings


def base_parts():
    dsn = settings.database_url.strip().strip('"').strip("'")
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn.removeprefix("postgresql+asyncpg://")
    p = urlparse(dsn)
    return p.username or "postgres", p.password or "", p.path or "/postgres"


async def try_dsn(label: str, dsn: str) -> None:
    import asyncpg

    red = re.sub(r":([^:@/]+)@", ":***@", dsn)
    try:
        conn = await asyncpg.connect(
            dsn, ssl="require", timeout=12, statement_cache_size=0
        )
        n = await conn.fetchval("select 1")
        await conn.close()
        print(f"OK  {label}: {red} -> {n}")
    except Exception as e:
        print(f"FAIL {label}: {type(e).__name__}: {e}")
        print(f"     {red}")


async def main() -> None:
    user, password, path = base_parts()
    ref = settings.project_ref
    pw = quote(password, safe="")

    candidates = [
        (
            "direct-5432",
            f"postgresql://{user}:{pw}@db.{ref}.supabase.co:5432{path}",
        ),
        (
            "pooler-session-5432",
            f"postgresql://postgres.{ref}:{pw}@aws-0-us-east-1.pooler.supabase.com:5432{path}",
        ),
        (
            "pooler-tx-6543",
            f"postgresql://postgres.{ref}:{pw}@aws-0-us-east-1.pooler.supabase.com:6543{path}",
        ),
        (
            "pooler-session-5432-aws1",
            f"postgresql://postgres.{ref}:{pw}@aws-1-us-east-1.pooler.supabase.com:5432{path}",
        ),
        (
            "pooler-tx-6543-user-postgres",
            f"postgresql://postgres:{pw}@aws-0-us-east-1.pooler.supabase.com:6543{path}",
        ),
    ]

    for label, dsn in candidates:
        await try_dsn(label, dsn)


if __name__ == "__main__":
    asyncio.run(main())
