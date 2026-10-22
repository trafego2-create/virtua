"""Mescla as exportações do Virtua e separa em clientes, contratos, acordos e parcelas.

Entrada (não versionada):
  Base Virtua.csv      relatório completo: valores, parcelas, acordos (fonte principal)
  Grade Excel 04.csv   mesmo universo de clientes, traz E-mail e UF

Saída em data/saida/: clientes.csv, contratos.csv, acordos.csv, parcelas.csv, conferencia.txt

Regras (definidas com a Wivianne em 14/10/2026):
  - parcela original citada num acordo -> status "renegociada" (não conta como atraso)
  - carteira ativa = cliente com acordo OU com vencimento a partir de CORTE_ATIVA
  - dentro da ativa: "em_dia" ou "em_atraso"
"""
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(r"C:\Users\trafe\Downloads\Base Virtua.csv")
EMAILS = Path(r"C:\Users\trafe\Downloads\Grade Excel 04.csv")
SAIDA = Path(__file__).resolve().parent.parent / "data" / "saida"
CORTE_ATIVA = date(2026, 1, 1)
HOJE = date.today()


def ler(caminho):
    linhas = list(csv.reader(caminho.read_text(encoding="latin1").splitlines(), delimiter=";"))
    cab, corpo = linhas[0], linhas[1:]
    totais = corpo[-1]  # última linha do relatório é a de totais
    return cab, [dict(zip(cab, l)) for l in corpo[:-1] if l and l[0].strip()], dict(zip(cab, totais))


def valor(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def data_br(s):
    """dd/mm/aaaa; aceita sem zero à esquerda ("8/4/2025"), formato usado em "Datas Envolvidas"."""
    partes = (s or "").strip().split("/")
    if len(partes) != 3 or not all(x.isdigit() for x in partes):
        return None
    d, m, a = (int(x) for x in partes)
    return date(a, m, d)


def tem_acordo(r):
    return r["Nr. Acordo"].strip() not in ("", "0")


def main():
    _, base, totais = ler(BASE)
    _, extra, _ = ler(EMAILS)

    # e-mail e UF por cliente (o campo às vezes repete o mesmo e-mail separado por ';')
    contato = {}
    for r in extra:
        emails = sorted({e.strip().lower() for e in r["E-mail"].split(";") if "@" in e})
        contato[r["Código"].strip()] = {"email": ";".join(emails), "uf": r["UF"].strip()}

    # parcelas originais renegociadas: (conta, vencimento) listados nos acordos
    renegociadas = set()
    for r in base:
        if tem_acordo(r):
            for d in r["Datas Envolvidas"].split(","):
                if data_br(d):
                    renegociadas.add((r["Conta"].strip(), data_br(d)))

    clientes, contratos, acordos, parcelas = {}, {}, {}, []
    for n, r in enumerate(base, start=1):
        cod = r["Cód. Cliente"].strip()
        conta = r["Conta"].strip()
        clientes.setdefault(cod, {
            "codigo": cod,
            "cpf_cnpj": r["CPF / CNPJ"].strip(),
            "nome": r["Nome do Cliente"].strip(),
            "telefone": r["FONE"].strip(),
            "email": contato.get(cod, {}).get("email", ""),
            "uf": contato.get(cod, {}).get("uf", ""),
        })
        acordo = r["Nr. Acordo"].strip() if tem_acordo(r) else ""
        if acordo:
            acordos.setdefault(acordo, {
                "nr_acordo": acordo,
                "codigo_cliente": cod,
                "conta": conta,
                "data_acordo": r["Data Acordo"].strip(),
                "valor_original": valor(r["Vlr. Original Acordo"]),
                "valor_desconto": valor(r["Vlr. Desconto Acordo"]),
                "valor_total": valor(r["Vlr. Total Acordo"]),
                "qtde_parcelas": r["Qtde Parcelas Acordo"].strip(),
                "vencimentos_renegociados": r["Datas Envolvidas"].strip(),
            })
        elif conta:
            contratos.setdefault(conta, {
                "conta": conta,
                "codigo_cliente": cod,
                "produto": r["Tipo Operação"].strip(),
                "lote": r["Garantias Reais"].strip(),
            })

        venc = data_br(r["Dta Vecto Parcela"])
        pago_em = data_br(r["Dta Pgto Parcela"])
        if pago_em:
            status = "paga"
        elif not acordo and (conta, venc) in renegociadas:
            status = "renegociada"
        elif venc and venc < HOJE:
            status = "vencida"
        else:
            status = "a_vencer"
        parcelas.append({
            "linha_origem": n,
            "codigo_cliente": cod,
            "conta": conta,
            "nr_acordo": acordo,
            "nr_parcela": r["Nr Parcela"].strip(),
            "vencimento": venc.isoformat() if venc else "",
            "valor_previsto": valor(r["Vlr. Previsto Parcela"]),
            "pago_em": pago_em.isoformat() if pago_em else "",
            "valor_pago": valor(r["Vlr. Realizado Parcela"]),
            "nosso_numero": r["Bol. Nosso Número"].strip(),
            "emissao_boleto": r["Dta Emissão Boleto"].strip(),
            "retirar_da_cobranca": "sim" if r["Classificação"].strip() else "",
            "status": status,
        })

    # carteira por cliente
    por_cliente = defaultdict(list)
    for p in parcelas:
        por_cliente[p["codigo_cliente"]].append(p)
    for cod, c in clientes.items():
        ps = por_cliente[cod]
        ativa = any(p["nr_acordo"] for p in ps) or any(
            p["vencimento"] and date.fromisoformat(p["vencimento"]) >= CORTE_ATIVA for p in ps)
        if not ativa:
            c["carteira"] = "inadimplencia_antiga"
        elif any(p["status"] == "vencida" for p in ps):
            c["carteira"] = "ativa_em_atraso"
        else:
            c["carteira"] = "ativa_em_dia"

    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, linhas in [("clientes", clientes.values()), ("contratos", contratos.values()),
                         ("acordos", acordos.values()), ("parcelas", parcelas)]:
        linhas = list(linhas)
        with open(SAIDA / f"{nome}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)

    conferir(base, totais, clientes, contratos, acordos, parcelas)


def conferir(base, totais, clientes, contratos, acordos, parcelas):
    out = []
    def linha(t=""):
        out.append(t)

    def ok(nome, esperado, obtido):
        marca = "OK " if abs(esperado - obtido) < 0.01 else "ERRO"
        linha(f"[{marca}] {nome}: Virtua {esperado:,.2f} | carregado {obtido:,.2f}")

    linha(f"Conferência gerada em {HOJE.isoformat()}")
    linha()
    linha("== Antigo x novo (linha de totais do Virtua) ==")
    ok("Linhas", int(totais["CPF / CNPJ"].replace(".", "")), len(parcelas))  # contagem vem como "28.384"
    ok("Valor previsto", valor(totais["Vlr. Previsto Parcela"]), sum(p["valor_previsto"] for p in parcelas))
    ok("Valor recebido", valor(totais["Vlr. Realizado Parcela"]), sum(p["valor_pago"] for p in parcelas))
    ok("Valor total de acordos", valor(totais["Vlr. Total Acordo"]),
       sum(valor(r["Vlr. Total Acordo"]) for r in base))
    linha()
    linha("== Contagens ==")
    linha(f"Clientes: {len(clientes)} | com e-mail: {sum(1 for c in clientes.values() if c['email'])}")
    linha(f"Contratos (vendas): {len(contratos)} | Acordos: {len(acordos)} | Parcelas: {len(parcelas)}")
    linha()
    linha("== Parcelas por status ==")
    st = defaultdict(lambda: [0, 0.0])
    for p in parcelas:
        st[p["status"]][0] += 1
        st[p["status"]][1] += p["valor_previsto"]
    for k in ("paga", "vencida", "renegociada", "a_vencer"):
        linha(f"{k:12} {st[k][0]:>6} parcelas  R$ {st[k][1]:>14,.2f}")
    linha()
    linha("== Carteira ==")
    cart = defaultdict(int)
    for c in clientes.values():
        cart[c["carteira"]] += 1
    for k in ("ativa_em_dia", "ativa_em_atraso", "inadimplencia_antiga"):
        linha(f"{k:22} {cart[k]:>5} clientes")
    atraso26 = sum(p["valor_previsto"] for p in parcelas
                   if p["status"] == "vencida" and p["vencimento"].startswith(str(CORTE_ATIVA.year)))
    linha(f"Atrasado com vencimento em {CORTE_ATIVA.year}: R$ {atraso26:,.2f}")
    linha()
    linha("== Pontos para o Financeiro ==")
    acordo_data = {a["nr_acordo"]: data_br(a["data_acordo"]) for a in acordos.values()}
    pago_antes = [p for p in parcelas if p["nr_acordo"] and p["pago_em"]
                  and acordo_data.get(p["nr_acordo"]) and date.fromisoformat(p["pago_em"]) < acordo_data[p["nr_acordo"]]]
    futuro = [p for p in parcelas if p["pago_em"] and date.fromisoformat(p["pago_em"]) > HOJE]
    linha(f"Parcelas de acordo pagas antes da data do acordo: {len(pago_antes)} (acordos {sorted({p['nr_acordo'] for p in pago_antes}, key=int)})")
    linha(f"Pagamentos com data futura: {len(futuro)} (linhas {[p['linha_origem'] for p in futuro]})")
    linha(f"Clientes sem e-mail: {[c['codigo'] for c in clientes.values() if not c['email']]}")
    linha(f"Parcelas marcadas 'RETIRAR DA COBRANCA': {sum(1 for p in parcelas if p['retirar_da_cobranca'])}")

    texto = "\n".join(out)
    (SAIDA / "conferencia.txt").write_text(texto, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
