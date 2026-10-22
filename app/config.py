"""Configuração lida do ambiente (EasyPanel → Environment; local → arquivo .env)."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Carrega o .env da raiz em desenvolvimento, sem sobrescrever o que já veio do ambiente."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# Postgres do Supabase (schema virtua). Obrigatório.
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não definida (veja .env.example)")

# Assina o cookie de sessão. Trocar este valor desloga todo mundo.
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
if not SESSION_SECRET:
    if PUBLIC_URL.startswith("https://"):
        raise RuntimeError("SESSION_SECRET é obrigatório em produção (gere com: python -c \"import secrets;print(secrets.token_urlsafe(48))\")")
    SESSION_SECRET = "dev-" + secrets.token_urlsafe(32)
COOKIE_SECURE = PUBLIC_URL.startswith("https://")
