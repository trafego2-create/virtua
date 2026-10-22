# Virtua — sistema de cobranças

Substitui o Virtua Software. FastAPI + Postgres (Supabase, schema `virtua`) + HTML/JS puro. Deploy no EasyPanel puxando deste repositório (`Dockerfile` na raiz).

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

## Carga da carteira (Virtua)
- **Pela tela** (administrador): menu *Importar*. Sobe o relatório completo do Virtua (+ o relatório com e-mail), vê a prévia e confirma.
- **Por script:** `scripts/carregar.py [completo.csv] [email.csv]` (padrão: os dois arquivos em Downloads).
- Os dois usam `app/importacao.py`: substitui o que veio do Virtua, mantém o que foi criado no sistema, confere os totais com a linha de totais do Virtua e não grava se não bater.

## Regras
- Parcela original citada num acordo = `renegociada` (não conta como atraso).
- Carteira ativa = cliente com acordo ou com vencimento a partir da data de corte (Configurações). Dentro dela: em dia / em atraso.
- Juros e multa (Configurações) só aparecem no "valor com juros e multa"; o valor da parcela não muda.
- Toda alteração vai para `virtua.auditoria` com o e-mail de quem fez (trigger no banco).

## Perfis
Administrador: tudo · Gestor: vê tudo + histórico · Financeiro: edita clientes, contratos e parcelas · Consulta: só vê.

## Testes
`tests/test_fluxo.py`, ponta a ponta contra o banco **local** (recarrega a carteira no fim).

## Deploy (EasyPanel novo, projeto `automacoes`, serviço `virtua`)
- Fonte: GitHub `trafego2-create/virtua`, branch `main`, caminho `/`, build Dockerfile.
- Environment: `DATABASE_URL` (Supabase comercial, pooler), `PUBLIC_URL`, `SESSION_SECRET`. Valores fora do git.
- Domínio: `automacoes-virtua.qacfzn.easypanel.host`, porta 8000.
- `scripts/publicar.py` (pacote no Storage + Dockerfile com link assinado) foi a alternativa de antes de existir o repo. Não precisa mais.
