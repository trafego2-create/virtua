# Etapa 1 — trava de build: JavaScript com erro de sintaxe derruba as telas.
# Se o front não passar no `node --check`, o build falha e o EasyPanel mantém a versão anterior.
FROM node:22-alpine AS checagem
WORKDIR /chk
COPY public/*.js ./
RUN for f in *.js; do node --check "$f" || exit 1; done && touch /chk/ok

# Etapa 2 — o app
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=checagem /chk/ok /tmp/js-ok
COPY app ./app
COPY public ./public
COPY schema.sql .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
# 1 worker: o controle de tentativas de login fica em memória
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
