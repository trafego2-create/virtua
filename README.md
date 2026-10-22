# Virtua — sistema de cobranças

Substitui o Virtua Software. FastAPI + Postgres (Supabase, schema `virtua`) + HTML/JS puro. Deploy no EasyPanel pelo `Dockerfile`.

## Rodar local
```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
# Postgres local (sem Docker): devdb/ tem o binário via npm "embedded-postgres"
devdb/node_modules/@embedded-postgres/windows-x64/native/bin/pg_ctl.exe -D devdb/pgdata -o "-p 54329" start
cp .env.example .env   # DATABASE_URL=postgresql://postgres:dev@localhost:54329/postgres
.venv/Scripts/python scripts/aplicar_schema.py
.venv/Scripts/python -m uvicorn app.main:app --reload
```
Na primeira abertura, a tela pede para criar a conta do administrador.

## Migração da carteira
1. `scripts/normalizar.py`: lê `Downloads\Base Virtua.csv` (valores) + `Downloads\Grade Excel 04.csv` (e-mail/UF) e gera `data/saida/*.csv` + `conferencia.txt` (antigo x novo).
2. `scripts/carregar.py`: grava no banco numa transação; confere os totais antes de confirmar. Recusa se já houver alterações feitas pelo sistema (use `--forcar` só antes da virada).

## Regras
- Parcela original citada num acordo = `renegociada` (não conta como atraso).
- Carteira ativa = cliente com acordo ou com vencimento a partir da data de corte (Configurações). Dentro dela: em dia / em atraso.
- Juros e multa (Configurações) só aparecem no "valor com juros e multa"; o valor da parcela não muda.
- Toda alteração vai para `virtua.auditoria` com o e-mail de quem fez (trigger no banco).

## Perfis
Administrador: tudo · Gestor: vê tudo + histórico · Financeiro: edita clientes, contratos e parcelas · Consulta: só vê.

## Testes
`tests/test_fluxo.py`, ponta a ponta contra o banco **local** (recarrega a carteira no fim).
