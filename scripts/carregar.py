"""Carrega data/saida/*.csv (gerados por normalizar.py) no schema virtua.

Uso:  python scripts/carregar.py            primeira carga ou recarga antes da virada
      python scripts/carregar.py --forcar   recarrega mesmo com alterações feitas pelo sistema

Apaga clientes/contratos/acordos/parcelas e grava tudo de novo, numa transação só.
Por isso recusa rodar se alguém já mexeu nos dados pelo sistema (a recarga apagaria isso).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
import psycopg  # noqa: E402

SAIDA = config.ROOT / "data" / "saida"


def ler(nome):
    with open(SAIDA / f"{nome}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def nulo(v):
    return v if v not in ("", None) else None


def main():
    forcar = "--forcar" in sys.argv
    clientes, contratos, acordos, parcelas = (ler(n) for n in ("clientes", "contratos", "acordos", "parcelas"))

    # toda conta citada por parcela ou acordo precisa existir em contratos
    contas = {c["conta"] for c in contratos}
    for p in parcelas + acordos:
        if p["conta"] and p["conta"] not in contas:
            contratos.append({"conta": p["conta"], "codigo_cliente": p["codigo_cliente"], "produto": "", "lote": ""})
            contas.add(p["conta"])

    with psycopg.connect(config.DATABASE_URL) as con:
        mexidos = con.execute(
            "select count(*) from virtua.auditoria where acao <> 'carga' and tabela in ('clientes','contratos','acordos','parcelas')"
        ).fetchone()[0]
        if mexidos and not forcar:
            sys.exit(f"Recusado: {mexidos} alterações feitas pelo sistema seriam apagadas. Use --forcar se for isso mesmo.")

        con.execute("set local virtua.sem_auditoria = 'on'")
        con.execute("truncate virtua.parcelas, virtua.acordos, virtua.contratos, virtua.clientes")

        with con.cursor().copy("copy virtua.clientes (codigo, cpf_cnpj, nome, telefone, email, uf) from stdin") as cp:
            for c in clientes:
                cp.write_row((c["codigo"], c["cpf_cnpj"], c["nome"], nulo(c["telefone"]), nulo(c["email"]), nulo(c["uf"])))
        with con.cursor().copy("copy virtua.contratos (conta, codigo_cliente, produto, lote) from stdin") as cp:
            for c in contratos:
                cp.write_row((c["conta"], c["codigo_cliente"], nulo(c["produto"]), nulo(c["lote"])))
        with con.cursor().copy(
            "copy virtua.acordos (nr_acordo, codigo_cliente, conta, data_acordo, valor_original, valor_desconto,"
            " valor_total, qtde_parcelas, vencimentos_renegociados) from stdin"
        ) as cp:
            for a in acordos:
                d = a["data_acordo"]
                cp.write_row((a["nr_acordo"], a["codigo_cliente"], nulo(a["conta"]),
                              f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if len(d) == 10 else None,
                              a["valor_original"], a["valor_desconto"], a["valor_total"],
                              nulo(a["qtde_parcelas"]), nulo(a["vencimentos_renegociados"])))
        with con.cursor().copy(
            "copy virtua.parcelas (codigo_cliente, conta, nr_acordo, nr_parcela, vencimento, valor_previsto, pago_em,"
            " valor_pago, nosso_numero, emissao_boleto, situacao, retirar_da_cobranca, linha_origem) from stdin"
        ) as cp:
            for p in parcelas:
                situacao = {"paga": "paga", "renegociada": "renegociada"}.get(p["status"], "aberta")
                cp.write_row((p["codigo_cliente"], nulo(p["conta"]), nulo(p["nr_acordo"]), nulo(p["nr_parcela"]),
                              p["vencimento"], p["valor_previsto"], nulo(p["pago_em"]), p["valor_pago"],
                              nulo(p["nosso_numero"]), nulo(p["emissao_boleto"]), situacao,
                              p["retirar_da_cobranca"] == "sim", p["linha_origem"]))

        con.execute("set local virtua.sem_auditoria = 'off'")
        con.execute(
            "insert into virtua.auditoria (usuario, tabela, registro, acao, depois) values ('migração', 'carteira', '*', 'carga', %s)",
            (psycopg.types.json.Jsonb({"clientes": len(clientes), "contratos": len(contratos),
                                       "acordos": len(acordos), "parcelas": len(parcelas)}),),
        )
        # conferência dentro da transação: se não bater, nada é gravado
        n, prev, pago = con.execute(
            "select count(*), sum(valor_previsto), sum(valor_pago) from virtua.parcelas").fetchone()
        esp_prev = round(sum(float(p["valor_previsto"]) for p in parcelas), 2)
        esp_pago = round(sum(float(p["valor_pago"]) for p in parcelas), 2)
        if n != len(parcelas) or float(prev) != esp_prev or float(pago) != esp_pago:
            raise SystemExit(f"Conferência falhou: banco {n}/{prev}/{pago} x arquivo {len(parcelas)}/{esp_prev}/{esp_pago}")

    print(f"Carregado: {len(clientes)} clientes, {len(contratos)} contratos, {len(acordos)} acordos, {len(parcelas)} parcelas")
    print(f"Previsto R$ {esp_prev:,.2f} | recebido R$ {esp_pago:,.2f} (batem com o arquivo)")


if __name__ == "__main__":
    main()
