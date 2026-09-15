# -*- coding: utf-8 -*-
"""
gerar_demo.py
--------------
Gera na hora um Excel de EXEMPLO com dados fictícios, sem abrir navegador,
para conferir o layout da planilha (resumo, gráficos e aba de itens).

Uso:
    python gerar_demo.py
"""

from robo_precos import config
from robo_precos.classify_export import montar_planilha, nome_arquivo_excel
from robo_precos.demo_data import produtos_demo


def main() -> None:
    saida = config.PASTA_SAIDA / nome_arquivo_excel(f"EXEMPLO_{config.PREFIXO_ARQUIVO_EXCEL}")
    print(f"[OK] Exemplo gerado em: {montar_planilha(produtos_demo(), saida)}")


if __name__ == "__main__":
    main()
