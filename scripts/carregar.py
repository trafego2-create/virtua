"""Carrega os relatórios do Virtua no schema virtua (mesma regra da tela "Importar do Virtua").

Uso:  python scripts/carregar.py [relatório completo] [relatório com e-mail] [--forcar]
      padrão: Downloads\\Base Virtua.csv e Downloads\\Grade Excel 04.csv

Mostra a prévia (conferência com os totais do Virtua e o que muda) e grava numa transação.
Recusa se a conferência não bater, ou se houver alterações feitas no sistema em parcelas do Virtua
desde a última carga (elas seriam sobrescritas); --forcar grava assim mesmo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, importacao  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

DOWNLOADS = Path.home() / "Downloads"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    forcar = "--forcar" in sys.argv
    caminhos = [Path(a) for a in sys.argv[1:] if not a.startswith("--")] or \
        [p for p in (DOWNLOADS / "Base Virtua.csv", DOWNLOADS / "Grade Excel 04.csv") if p.exists()]
    dados = importacao.ler_arquivos([(p.name, p.read_bytes()) for p in caminhos])
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row, prepare_threshold=None) as con:
        p = importacao.previa(con, dados)
        for c in p["conferencia"]:
            print(f"[{'OK ' if c['ok'] else 'ERRO'}] {c['item']}: Virtua {c['virtua']} | lido {c['lido']}")
        print(f"clientes {p['contagens']['clientes']} (novos {p['qtd_clientes_novos']}, saíram {p['qtd_clientes_sairam']}) · "
              f"parcelas {p['contagens']['parcelas']} (novas {p['parcelas_novas']}, removidas {p['parcelas_removidas']}) · "
              f"pagamentos novos {p['qtd_pagamentos_novos']} (R$ {p['valor_pagamentos_novos']}) · sem e-mail {p['contagens']['sem_email']} · "
              f"duplicadas descartadas {p['qtd_duplicadas']} (R$ {p['valor_duplicadas']})")
        if not p["pode_confirmar"]:
            sys.exit("Recusado: a conferência com os totais do Virtua não bateu.")
        if p["conflitos"] and not forcar:
            sys.exit(f"Recusado: {len(p['conflitos'])} alterações feitas no sistema seriam sobrescritas. Use --forcar se for isso mesmo.")
        with con.transaction():
            r = importacao.aplicar(con, dados, "script de carga")
    print(f"Carregado: {r['clientes']} clientes, {r['contratos']} contratos, {r['acordos']} acordos, {r['parcelas']} parcelas "
          f"(previsto R$ {r['previsto']}, recebido R$ {r['recebido']}; {r['clientes_removidos']} clientes saíram)")


if __name__ == "__main__":
    main()
