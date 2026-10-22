"""Empacota o código, sobe no Storage do Supabase (bucket privado) e gera o Dockerfile do EasyPanel.

Uso: python scripts/publicar.py   (lê SUPABASE_URL e SUPABASE_SERVICE_KEY do .env.producao)
Saída: data/Dockerfile.easypanel, para colar como fonte "Dockerfile" do app no EasyPanel.

O Dockerfile baixa o pacote por um link assinado e confere o sha256 antes de instalar:
se o arquivo não for exatamente o que foi publicado, o build falha e a versão anterior fica no ar.
Quando o código for para o GitHub, trocar a fonte do app para o repo e usar o Dockerfile normal.
"""
import hashlib
import io
import json
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUCKET = "virtua-deploy"
VALIDADE_S = 7 * 86400  # o link só é usado no build; rebuild depois disso exige publicar de novo
ARQUIVOS = sorted([*RAIZ.glob("app/*.py"), *RAIZ.glob("public/*"), RAIZ / "schema.sql", RAIZ / "requirements.txt"])


def env():
    vals = {}
    for linha in (RAIZ / ".env.producao").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals["SUPABASE_URL"].rstrip("/"), vals["SUPABASE_SERVICE_KEY"]


def chamar(metodo, url, chave, corpo=None, tipo="application/json"):
    req = urllib.request.Request(url, data=corpo, method=metodo,
                                 headers={"Authorization": f"Bearer {chave}", "apikey": chave, "Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    for a in ARQUIVOS:
        if a.suffix == ".js":
            subprocess.run(["node", "--check", str(a)], check=True)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for a in ARQUIVOS:
            dados = a.read_bytes().replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(a.relative_to(RAIZ).as_posix())
            info.size, info.mtime, info.mode = len(dados), 0, 0o644
            tar.addfile(info, io.BytesIO(dados))
    pacote = buf.getvalue()
    soma = hashlib.sha256(pacote).hexdigest()
    nome = f"virtua-{time.strftime('%Y%m%d-%H%M%S')}-{soma[:8]}.tar.gz"

    url, chave = env()
    st, _ = chamar("POST", f"{url}/storage/v1/bucket", chave,
                   json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode())
    if st not in (200, 201, 400, 409):  # 400/409 = bucket já existe
        raise SystemExit(f"falha ao criar bucket: {st}")
    st, corpo = chamar("POST", f"{url}/storage/v1/object/{BUCKET}/{nome}", chave, pacote, "application/gzip")
    if st not in (200, 201):
        raise SystemExit(f"falha no upload: {st} {corpo[:200]!r}")
    st, corpo = chamar("POST", f"{url}/storage/v1/object/sign/{BUCKET}/{nome}", chave,
                       json.dumps({"expiresIn": VALIDADE_S}).encode())
    if st != 200:
        raise SystemExit(f"falha ao assinar link: {st} {corpo[:200]!r}")
    link = url + "/storage/v1" + json.loads(corpo)["signedURL"]

    dockerfile = f"""# GERADO por scripts/publicar.py em {time.strftime('%d/%m/%Y %H:%M')} ({nome})
FROM python:3.12-slim
WORKDIR /app
RUN python -c "import urllib.request; urllib.request.urlretrieve('{link}', '/tmp/codigo.tar.gz')" \\
 && echo '{soma}  /tmp/codigo.tar.gz' | sha256sum -c - \\
 && tar xzf /tmp/codigo.tar.gz -C /app && rm /tmp/codigo.tar.gz \\
 && pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
"""
    saida = RAIZ / "data" / "Dockerfile.easypanel"
    saida.write_text(dockerfile, encoding="utf-8", newline="\n")
    print(f"publicado {nome} ({len(pacote) // 1024} KB, sha256 {soma[:12]}) -> {saida}")


if __name__ == "__main__":
    main()
