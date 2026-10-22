"""Aplica o schema.sql no banco da DATABASE_URL (idempotente)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
import psycopg  # noqa: E402

sql = (config.ROOT / "schema.sql").read_text(encoding="utf-8")
with psycopg.connect(config.DATABASE_URL, autocommit=True) as con:
    if not con.execute("select 1 from pg_roles where rolname = 'anon'").fetchone():
        # Postgres local de desenvolvimento: cria os papéis que o Supabase já tem
        con.execute("create role anon nologin; create role authenticated nologin")
    con.execute(sql)
print("schema virtua aplicado")
