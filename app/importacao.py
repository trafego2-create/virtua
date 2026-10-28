"""Importação dos relatórios do Virtua: leitura, prévia (o que muda) e gravação.

Usado pela tela "Importar do Virtua" e pelos scripts (normalizar.py / carregar.py), para as duas
formas de carga seguirem exatamente a mesma regra.

Arquivos (exportados do Virtua, latin1, separador ';', última linha = totais):
  relatório completo  ("Base Virtua")      → valores, parcelas, acordos   (identificado por "Vlr. Previsto Parcela")
  relatório com e-mail ("Grade Excel 04")  → e-mail e UF de cada cliente (identificado por "E-mail" + "Código")

Regras (definidas com a Wivianne em 14/10/2026):
  - parcela original citada num acordo → "renegociada" (não conta como atraso)
  - enquanto o Virtua estiver em uso, ele é a fonte oficial: a importação SUBSTITUI o que veio dele
    (origem 'virtua') e MANTÉM o que foi criado no sistema (origem 'sistema', clientes N-…, observações)

previa() e aplicar() esperam conexão com row_factory=dict_row (a do app já é assim).
"""
import csv
import io
import re
from datetime import date
from decimal import Decimal

from psycopg.types.json import Jsonb

COLUNAS_BASE = {"Cód. Cliente", "CPF / CNPJ", "Nome do Cliente", "Conta", "Nr. Acordo", "Dta Vecto Parcela",
                "Dta Pgto Parcela", "Vlr. Previsto Parcela", "Vlr. Realizado Parcela", "Datas Envolvidas"}
COLUNAS_EMAIL = {"Código", "E-mail", "UF"}


class ArquivoInvalido(ValueError):
    pass


# ---------- leitura ----------
def _texto(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("latin1")  # o Virtua exporta em latin1


def ler_relatorio(conteudo: bytes) -> tuple[str, list[dict], dict]:
    """Devolve (tipo, linhas, totais); tipo = 'base' ou 'email'."""
    linhas = list(csv.reader(io.StringIO(_texto(conteudo)), delimiter=";"))
    if len(linhas) < 3:
        raise ArquivoInvalido("arquivo vazio ou sem a linha de totais")
    cab = [c.strip() for c in linhas[0]]
    if COLUNAS_BASE <= set(cab):
        tipo = "base"
    elif COLUNAS_EMAIL <= set(cab):
        tipo = "email"
    else:
        raise ArquivoInvalido("não parece um relatório do Virtua (colunas esperadas não encontradas)")
    corpo, totais = linhas[1:-1], dict(zip(cab, linhas[-1]))
    return tipo, [dict(zip(cab, l)) for l in corpo if l and l[0].strip() and len(l) >= len(cab) - 2], totais


def valor(s) -> Decimal:
    s = (s or "").strip()
    if not s:
        return Decimal("0")
    if "," in s:                                   # 1.234,56
        return Decimal(s.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):      # 1.225 = mil duzentos e vinte e cinco
        return Decimal(s.replace(".", ""))
    return Decimal(s)


def data_br(s) -> date | None:
    """dd/mm/aaaa; aceita sem zero à esquerda ("8/4/2025"), formato usado em "Datas Envolvidas"."""
    partes = (s or "").strip().split("/")
    if len(partes) != 3 or not all(x.isdigit() for x in partes):
        return None
    d, m, a = (int(x) for x in partes)
    return date(a, m, d)


def _nulo(v):
    v = (v or "").strip()
    return v or None


# ---------- normalização ----------
def normalizar(base: list[dict], totais: dict, extra: list[dict]) -> dict:
    contato = {}
    for r in extra:
        emails = sorted({e.strip().lower() for e in (r.get("E-mail") or "").split(";") if "@" in e})
        contato[r["Código"].strip()] = {"email": ";".join(emails) or None, "uf": _nulo(r.get("UF"))}

    tem_acordo = lambda r: (r.get("Nr. Acordo") or "").strip() not in ("", "0")  # noqa: E731
    renegociadas = set()
    for r in base:
        if tem_acordo(r):
            for d in (r.get("Datas Envolvidas") or "").split(","):
                if data_br(d):
                    renegociadas.add((r["Conta"].strip(), data_br(d)))

    clientes, contratos, acordos, parcelas = {}, {}, {}, []
    for n, r in enumerate(base, start=1):
        cod, conta = r["Cód. Cliente"].strip(), _nulo(r.get("Conta"))
        clientes.setdefault(cod, {
            "codigo": cod, "cpf_cnpj": r["CPF / CNPJ"].strip(), "nome": r["Nome do Cliente"].strip(),
            "telefone": _nulo(r.get("FONE")), "email": contato.get(cod, {}).get("email"), "uf": contato.get(cod, {}).get("uf"),
        })
        acordo = r["Nr. Acordo"].strip() if tem_acordo(r) else None
        if acordo:
            acordos.setdefault(acordo, {
                "nr_acordo": acordo, "codigo_cliente": cod, "conta": conta, "data_acordo": data_br(r.get("Data Acordo")),
                "valor_original": valor(r.get("Vlr. Original Acordo")), "valor_desconto": valor(r.get("Vlr. Desconto Acordo")),
                "valor_total": valor(r.get("Vlr. Total Acordo")), "qtde_parcelas": _nulo(r.get("Qtde Parcelas Acordo")),
                "vencimentos_renegociados": _nulo(r.get("Datas Envolvidas")),
            })
        if conta and conta not in contratos:
            contratos[conta] = {"conta": conta, "codigo_cliente": cod,
                                "produto": None if acordo else _nulo(r.get("Tipo Operação")),
                                "lote": None if acordo else _nulo(r.get("Garantias Reais"))}
        elif conta and not acordo and contratos[conta]["produto"] is None:
            contratos[conta] |= {"produto": _nulo(r.get("Tipo Operação")), "lote": _nulo(r.get("Garantias Reais"))}

        venc, pago_em = data_br(r["Dta Vecto Parcela"]), data_br(r.get("Dta Pgto Parcela"))
        if venc is None:
            raise ArquivoInvalido(f"linha {n + 1}: vencimento inválido ({r['Dta Vecto Parcela']!r})")
        if pago_em:
            situacao = "paga"
        elif not acordo and (conta, venc) in renegociadas:
            situacao = "renegociada"
        else:
            situacao = "aberta"
        parcelas.append({
            "codigo_cliente": cod, "conta": conta, "nr_acordo": acordo, "nr_parcela": _nulo(r.get("Nr Parcela")),
            "vencimento": venc, "valor_previsto": valor(r["Vlr. Previsto Parcela"]), "pago_em": pago_em,
            "valor_pago": valor(r.get("Vlr. Realizado Parcela")), "nosso_numero": _nulo(r.get("Bol. Nosso Número")),
            "emissao_boleto": _nulo(r.get("Dta Emissão Boleto")),
            "retirar_da_cobranca": bool((r.get("Classificação") or "").strip()), "situacao": situacao, "linha_origem": n,
            "ficha": _nulo(r.get("Nr. Ficha")),
        })

    # a conferência é com todas as linhas do arquivo: a linha de totais do Virtua também soma as duplicadas
    conferencia = [
        ("Parcelas", int(re.sub(r"\D", "", totais.get("CPF / CNPJ", "")) or 0), len(parcelas)),
        ("Valor previsto", valor(totais.get("Vlr. Previsto Parcela")), sum(p["valor_previsto"] for p in parcelas)),
        ("Valor recebido", valor(totais.get("Vlr. Realizado Parcela")), sum(p["valor_pago"] for p in parcelas)),
        ("Total de acordos", valor(totais.get("Vlr. Total Acordo")), sum(valor(r.get("Vlr. Total Acordo")) for r in base)),
    ]
    parcelas, duplicadas = _sem_duplicadas(parcelas)
    return {
        "clientes": list(clientes.values()), "contratos": list(contratos.values()),
        "acordos": list(acordos.values()), "parcelas": parcelas, "duplicadas": duplicadas,
        "conferencia": [{"item": i, "virtua": v, "lido": l, "ok": v == l} for i, v, l in conferencia],
        "sem_email": sum(1 for c in clientes.values() if not c["email"]),
    }


def _sem_duplicadas(parcelas: list[dict]) -> tuple[list[dict], list[dict]]:
    """O Virtua às vezes exporta a mesma dívida em 2 linhas (mesmo contrato, ficha, vencimento e valor; "Nr Parcela" 1 e 2),
    mas na tela dele a dívida conta uma vez só (caso Karen, cód. 4985, apontado pela Mayane em 28/10/2026).
    Fica uma linha por dívida; se alguma cópia está paga, ficam só as pagas (o dinheiro entrou)."""
    grupos = {}
    for p in parcelas:
        if p["nr_acordo"]:  # parcelas de acordo não entram nessa regra
            grupos[id(p)] = [p]
            continue
        grupos.setdefault((p["conta"], p["ficha"], p["vencimento"], p["valor_previsto"]), []).append(p)
    ficam, saem = [], []
    for ps in grupos.values():
        pagas = [p for p in ps if p["pago_em"]]
        manter = pagas or ps[:1]
        ficam += manter
        saem += [p for p in ps if all(p is not m for m in manter)]
    ficam.sort(key=lambda p: p["linha_origem"])
    return ficam, saem


def ler_arquivos(arquivos: list[tuple[str, bytes]]) -> dict:
    """arquivos = [(nome, conteúdo)] na ordem que vier; identifica cada um pelo cabeçalho."""
    lidos = {}
    for nome, conteudo in arquivos:
        try:
            tipo, linhas, totais = ler_relatorio(conteudo)
        except ArquivoInvalido as e:
            raise ArquivoInvalido(f"{nome}: {e}") from None
        if tipo in lidos:
            raise ArquivoInvalido(f"{nome} e {lidos[tipo][0]} são o mesmo tipo de relatório")
        lidos[tipo] = (nome, linhas, totais)
    if "base" not in lidos:
        raise ArquivoInvalido("falta o relatório completo (o que tem 'Vlr. Previsto Parcela')")
    extra = lidos["email"][1] if "email" in lidos else []
    dados = normalizar(lidos["base"][1], lidos["base"][2], extra)
    dados["arquivos"] = {t: v[0] for t, v in lidos.items()}
    if extra:
        cods = {c["codigo"] for c in dados["clientes"]}
        dados["email_fora_da_base"] = len({r["Código"].strip() for r in extra} - cods)
    return dados


# ---------- prévia ----------
def _chave(p) -> tuple:
    return (p["conta"], p["nr_acordo"], str(p["nr_parcela"] or ""), p["vencimento"])


def previa(con, dados: dict) -> dict:
    """Compara o que está no banco (origem virtua) com o que vai entrar."""
    atual = con.execute("""select codigo_cliente, conta, nr_acordo, nr_parcela, vencimento, valor_previsto, pago_em,
                                  valor_pago, situacao from virtua.parcelas where origem = 'virtua'""").fetchall()
    antes = {}
    for p in atual:  # cópias duplicadas de cargas antigas têm a mesma chave: vale a paga, senão vira "pagamento novo"
        if _chave(p) not in antes or p["pago_em"]:
            antes[_chave(p)] = p
    depois = {_chave(p): p for p in dados["parcelas"]}
    nomes = {c["codigo"]: c["nome"] for c in dados["clientes"]}
    nomes |= {r["codigo"]: r["nome"] for r in con.execute("select codigo, nome from virtua.clientes").fetchall()}

    novas = [p for k, p in depois.items() if k not in antes]
    removidas = [p for k, p in antes.items() if k not in depois]
    pagamentos = [p for k, p in depois.items() if p["pago_em"] and k in antes and not antes[k]["pago_em"]]
    estornos = [p for k, p in depois.items() if not p["pago_em"] and k in antes and antes[k]["pago_em"]]
    cli_atual = {r["codigo"] for r in con.execute("select codigo from virtua.clientes where codigo not like 'N-%%'").fetchall()}
    cli_novo = {c["codigo"] for c in dados["clientes"]}

    # alterações feitas pelo sistema em parcelas do Virtua depois da última carga → serão sobrescritas
    ultima = con.execute("select max(id) as id, max(em) as em from virtua.auditoria where acao = 'carga'").fetchone()
    conflitos = con.execute("""
        select a.em, a.usuario, a.antes, a.depois, c.nome
        from virtua.auditoria a
        join virtua.parcelas p on p.id::text = a.registro and p.origem = 'virtua'
        join virtua.clientes c on c.codigo = p.codigo_cliente
        where a.tabela = 'parcelas' and a.acao = 'alterou' and a.id > coalesce(%s, 0)
        order by a.em""", (ultima["id"],)).fetchall()
    mantidos = con.execute("""select (select count(*) from virtua.clientes where codigo like 'N-%%') as clientes,
                                     (select count(*) from virtua.contratos where origem = 'sistema') as contratos,
                                     (select count(*) from virtua.parcelas where origem = 'sistema') as parcelas""").fetchone()

    def resumo(ps, limite=200):
        return [{"cliente": nomes.get(p["codigo_cliente"], p["codigo_cliente"]), "codigo": p["codigo_cliente"],
                 "vencimento": p["vencimento"], "valor": p["valor_previsto"], "pago_em": p["pago_em"],
                 "valor_pago": p["valor_pago"], "acordo": p["nr_acordo"]} for p in ps[:limite]]

    return {
        "ultima_carga": ultima["em"],
        "conferencia": dados["conferencia"],
        "pode_confirmar": all(c["ok"] for c in dados["conferencia"]),
        "arquivos": dados["arquivos"],
        "contagens": {"clientes": len(dados["clientes"]), "contratos": len(dados["contratos"]),
                      "acordos": len(dados["acordos"]), "parcelas": len(dados["parcelas"]), "sem_email": dados["sem_email"]},
        "sem_arquivo_email": "email" not in dados["arquivos"],
        "clientes_novos": sorted(nomes.get(c, c) for c in cli_novo - cli_atual)[:200],
        "qtd_clientes_novos": len(cli_novo - cli_atual),
        "qtd_clientes_sairam": len(cli_atual - cli_novo),
        "parcelas_novas": len(novas), "parcelas_removidas": len(removidas),
        "pagamentos_novos": resumo(sorted(pagamentos, key=lambda p: p["pago_em"], reverse=True)),
        "qtd_pagamentos_novos": len(pagamentos), "valor_pagamentos_novos": sum(p["valor_pago"] for p in pagamentos),
        "estornos": resumo(estornos), "qtd_estornos": len(estornos),
        "duplicadas": resumo(dados["duplicadas"]), "qtd_duplicadas": len(dados["duplicadas"]),
        "valor_duplicadas": sum(p["valor_previsto"] for p in dados["duplicadas"]),
        "conflitos": [{"em": c["em"], "usuario": c["usuario"], "cliente": c["nome"],
                       "vencimento": (c["depois"] or {}).get("vencimento"),
                       "mudou": sorted(k for k in (c["depois"] or {}) if k not in ("atualizado_em",)
                                       and (c["antes"] or {}).get(k) != (c["depois"] or {}).get(k))} for c in conflitos],
        "mantidos": mantidos,
    }


# ---------- gravação ----------
def aplicar(con, dados: dict, usuario: str) -> dict:
    """Substitui o que veio do Virtua, mantém o que foi criado no sistema. Roda dentro de uma transação."""
    con.execute("set local virtua.sem_auditoria = 'on'")
    con.execute("delete from virtua.parcelas where origem = 'virtua'")
    con.execute("delete from virtua.acordos")  # acordos só vêm do Virtua
    con.execute("delete from virtua.contratos where origem = 'virtua'")

    # clientes não é apagada (guarda observações e clientes criados no sistema): entra por upsert
    con.execute("create temp table _cli (like virtua.clientes including defaults) on commit drop")
    with con.cursor().copy("copy _cli (codigo, cpf_cnpj, nome, telefone, email, uf) from stdin") as cp:
        for c in dados["clientes"]:
            cp.write_row((c["codigo"], c["cpf_cnpj"], c["nome"], c["telefone"], c["email"], c["uf"]))
    con.execute("""insert into virtua.clientes (codigo, cpf_cnpj, nome, telefone, email, uf)
                   select codigo, cpf_cnpj, nome, telefone, email, uf from _cli
                   on conflict (codigo) do update set cpf_cnpj = excluded.cpf_cnpj, nome = excluded.nome,
                       telefone = excluded.telefone, email = coalesce(excluded.email, virtua.clientes.email),
                       uf = coalesce(excluded.uf, virtua.clientes.uf)""")
    with con.cursor().copy("copy virtua.contratos (conta, codigo_cliente, produto, lote) from stdin") as cp:
        for c in dados["contratos"]:
            cp.write_row((c["conta"], c["codigo_cliente"], c["produto"], c["lote"]))
    with con.cursor().copy("copy virtua.acordos (nr_acordo, codigo_cliente, conta, data_acordo, valor_original, valor_desconto,"
                           " valor_total, qtde_parcelas, vencimentos_renegociados) from stdin") as cp:
        for a in dados["acordos"]:
            cp.write_row((a["nr_acordo"], a["codigo_cliente"], a["conta"], a["data_acordo"], a["valor_original"],
                          a["valor_desconto"], a["valor_total"], a["qtde_parcelas"], a["vencimentos_renegociados"]))
    with con.cursor().copy("copy virtua.parcelas (codigo_cliente, conta, nr_acordo, nr_parcela, vencimento, valor_previsto, pago_em,"
                           " valor_pago, nosso_numero, emissao_boleto, situacao, retirar_da_cobranca, linha_origem) from stdin") as cp:
        for p in dados["parcelas"]:
            cp.write_row((p["codigo_cliente"], p["conta"], p["nr_acordo"], p["nr_parcela"], p["vencimento"], p["valor_previsto"],
                          p["pago_em"], p["valor_pago"], p["nosso_numero"], p["emissao_boleto"], p["situacao"],
                          p["retirar_da_cobranca"], p["linha_origem"]))
    # cliente que saiu do Virtua e não tem nada criado no sistema deixa de existir
    saiu = con.execute("""delete from virtua.clientes c where c.codigo not like 'N-%%'
                            and not exists (select 1 from _cli n where n.codigo = c.codigo)
                            and not exists (select 1 from virtua.parcelas p where p.codigo_cliente = c.codigo)
                            and not exists (select 1 from virtua.contratos k where k.codigo_cliente = c.codigo)""").rowcount

    # conferência dentro da transação: se não bater, nada é gravado
    t = con.execute("""select count(*) as n, coalesce(sum(valor_previsto), 0) as prev, coalesce(sum(valor_pago), 0) as pago
                       from virtua.parcelas where origem = 'virtua'""").fetchone()
    n, prev, pago = t["n"], t["prev"], t["pago"]
    esp_prev = sum(p["valor_previsto"] for p in dados["parcelas"])
    esp_pago = sum(p["valor_pago"] for p in dados["parcelas"])
    if n != len(dados["parcelas"]) or prev != esp_prev or pago != esp_pago:
        raise RuntimeError(f"conferência falhou: banco {n}/{prev}/{pago} x arquivo {len(dados['parcelas'])}/{esp_prev}/{esp_pago}")

    resumo = {"arquivos": dados["arquivos"], "clientes": len(dados["clientes"]), "contratos": len(dados["contratos"]),
              "acordos": len(dados["acordos"]), "parcelas": n, "previsto": str(prev), "recebido": str(pago),
              "clientes_removidos": saiu}
    con.execute("set local virtua.sem_auditoria = 'off'")
    con.execute("insert into virtua.auditoria (usuario, tabela, registro, acao, depois) values (%s, 'carteira', '*', 'carga', %s)",
                (usuario, Jsonb(resumo)))
    return resumo
