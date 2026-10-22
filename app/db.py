"""Pool de conexões. Toda escrita passa por tx(usuario), que grava quem fez para o histórico."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

# prepare_threshold=None: o pooler do Supabase (pgbouncer) não aceita prepared statements
pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row, "prepare_threshold": None})


def all(sql: str, params=None) -> list[dict]:
    with pool.connection() as con:
        return con.execute(sql, params).fetchall()


def one(sql: str, params=None) -> dict | None:
    with pool.connection() as con:
        return con.execute(sql, params).fetchone()


@contextmanager
def tx(usuario: str):
    with pool.connection() as con, con.transaction():
        con.execute("select set_config('virtua.usuario', %s, true)", (usuario,))
        yield con
