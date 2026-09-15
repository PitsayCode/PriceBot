# -*- coding: utf-8 -*-
"""
classify_export.py
--------------------
Monta o Excel final com duas abas:

    Resumo -> indicadores (total, menor, médio, mediana, maior), limites das
              faixas, contagem por faixa, tabela por categoria e 2 gráficos.
    Itens  -> um produto por linha (tabela do Excel com filtro), com faixa
              de preço e ranking calculados por FÓRMULA.

Os limites das faixas ficam em células da aba Resumo (C11 e C12) e as
fórmulas da aba Itens apontam para elas: se você editar um limite, todas
as classificações, contagens e gráficos se atualizam sozinhos.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from . import config
from .analise import FAIXAS, Resumo, resumir
from .modelos import Produto

FONTE = "Arial"
COR_TITULO = "3B2A9E"
COR_CABECALHO = "1F2A44"
COR_SUAVE = "6B7280"
COR_ENTRADA = "1D4ED8"          # azul = valor editável (convenção de planilhas)
COR_LINHA = "E5E7EB"
CORES_FAIXA = {                 # (fundo, texto, cor no gráfico)
    "Econômico": ("D1FAE5", "065F46", "34D399"),
    "Intermediário": ("FEF3C7", "92400E", "FBBF24"),
    "Premium": ("FCE7F3", "9D174D", "F472B6"),
}

LIMITE_ECONOMICO = "Resumo!$C$11"
LIMITE_INTERMEDIARIO = "Resumo!$C$12"

CABECALHO_ITENS = ["ID", "Produto", "Marca", "Grupo", "Subcategoria", "Moeda",
                   "Preço", "Faixa de preço", "Ranking", "Link"]
LARGURAS_ITENS = [8, 46, 20, 12, 18, 8, 15, 17, 10, 46]


def nome_arquivo_excel(prefixo: str = config.PREFIXO_ARQUIVO_EXCEL, momento: datetime | None = None) -> str:
    momento = momento or datetime.now()
    return f"{prefixo}_{momento:%Y-%m-%d_%H%M%S}.xlsx"


def _fonte(**kwargs) -> Font:
    return Font(name=FONTE, **kwargs)


def _preenchimento(cor: str) -> PatternFill:
    return PatternFill(start_color=cor, end_color=cor, fill_type="solid")


def _larguras(ws: Worksheet, larguras: list[int]) -> None:
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura


def _preencher_itens(ws: Worksheet, produtos: list[Produto], ultima: int, formato_preco: str) -> None:
    for col, titulo in enumerate(CABECALHO_ITENS, start=1):
        c = ws.cell(row=1, column=col, value=titulo)
        c.font = _fonte(bold=True, color="FFFFFF")
        c.fill = _preenchimento(COR_CABECALHO)
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    for i, p in enumerate(produtos):
        linha = i + 2
        valores = [
            int(p.id_produto) if p.id_produto.isdigit() else p.id_produto,
            p.nome, p.marca, p.categoria_grupo, p.categoria_sub, p.moeda, p.preco_valor,
            f'=IF(G{linha}<={LIMITE_ECONOMICO},"Econômico",'
            f'IF(G{linha}<={LIMITE_INTERMEDIARIO},"Intermediário","Premium"))',
            f"=RANK(G{linha},$G$2:$G${ultima})",
            p.url,
        ]
        for col, valor in enumerate(valores, start=1):
            ws.cell(row=linha, column=col, value=valor).font = _fonte()

        ws.cell(row=linha, column=1).alignment = Alignment(horizontal="center")
        ws.cell(row=linha, column=6).alignment = Alignment(horizontal="center")
        ws.cell(row=linha, column=7).number_format = formato_preco
        ws.cell(row=linha, column=8).alignment = Alignment(horizontal="center")
        ws.cell(row=linha, column=9).alignment = Alignment(horizontal="center")
        if p.url:
            link = ws.cell(row=linha, column=10)
            link.hyperlink = p.url
            link.font = _fonte(color="2563EB", underline="single")

    tabela = Table(displayName="TabelaItens", ref=f"A1:J{ultima}")
    tabela.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(tabela)

    for faixa, (fundo, texto, _) in CORES_FAIXA.items():
        ws.conditional_formatting.add(
            f"H2:H{ultima}",
            CellIsRule(operator="equal", formula=[f'"{faixa}"'],
                       fill=_preenchimento(fundo), font=Font(color=texto, bold=True)),
        )
    ws.conditional_formatting.add(
        f"G2:G{ultima}",
        DataBarRule(start_type="num", start_value=0, end_type="max", color="A78BFA", showValue=True),
    )

    ws.cell(row=1, column=8).comment = Comment(
        "Calculada por fórmula usando os limites editáveis da aba Resumo "
        "(células C11 e C12).",
        config.APP_NOME,
    )
    ws.freeze_panes = "C2"
    _larguras(ws, LARGURAS_ITENS)


def _secao(ws: Worksheet, linha: int, titulo: str) -> None:
    c = ws.cell(row=linha, column=2, value=titulo)
    c.font = _fonte(bold=True, size=10, color=COR_TITULO)


def _cabecalho_tabela(ws: Worksheet, linha: int, titulos: list[str]) -> None:
    for col, titulo in enumerate(titulos, start=2):
        c = ws.cell(row=linha, column=col, value=titulo)
        c.font = _fonte(bold=True, color="FFFFFF")
        c.fill = _preenchimento(COR_CABECALHO)
        c.alignment = Alignment(horizontal="left" if col == 2 else "center", vertical="center")


def _linha_fina(ws: Worksheet, linha: int, col_ini: int, col_fim: int) -> None:
    borda = Border(bottom=Side(style="thin", color=COR_LINHA))
    for col in range(col_ini, col_fim + 1):
        ws.cell(row=linha, column=col).border = borda


def _preencher_resumo(ws: Worksheet, resumo: Resumo, ultima: int, formato_preco: str, gerado_em: datetime) -> None:
    ws.sheet_view.showGridLines = False
    _larguras(ws, [3, 34, 16, 16, 15, 15, 3])

    ws["B2"] = "Relatório de preços — automationexercise.com"
    ws["B2"].font = _fonte(bold=True, size=18, color=COR_TITULO)
    ws["B3"] = (
        f"Gerado por {config.APP_NOME} em {gerado_em:%d/%m/%Y às %H:%M} · "
        f"{resumo.total} produtos · faixas pelos percentis 33% e 66%"
    )
    ws["B3"].font = _fonte(italic=True, color=COR_SUAVE)

    precos = f"Itens!$G$2:$G${ultima}"

    # --- Indicadores (linhas 6 a 12) --------------------------------------
    _secao(ws, 5, "INDICADORES")
    indicadores = [
        ("Total de produtos", f"=COUNTA(Itens!$B$2:$B${ultima})", "0"),
        ("Menor preço", f"=MIN({precos})", formato_preco),
        ("Preço médio", f"=AVERAGE({precos})", formato_preco),
        ("Mediana", f"=MEDIAN({precos})", formato_preco),
        ("Maior preço", f"=MAX({precos})", formato_preco),
        ("Limite Econômico (até)", resumo.limites[0], formato_preco),
        ("Limite Intermediário (até)", resumo.limites[1], formato_preco),
    ]
    for i, (rotulo, valor, formato) in enumerate(indicadores):
        linha = 6 + i
        ws.cell(row=linha, column=2, value=rotulo).font = _fonte()
        c = ws.cell(row=linha, column=3, value=valor)
        c.number_format = formato
        c.alignment = Alignment(horizontal="right")
        editavel = isinstance(valor, float)
        c.font = _fonte(bold=True, color=COR_ENTRADA if editavel else "111827")
        _linha_fina(ws, linha, 2, 3)
    ws["C11"].comment = Comment(
        "Valores editáveis. Calculados pelos percentis 33% e 66% dos preços desta "
        "coleta; altere para reclassificar todos os itens.",
        config.APP_NOME,
    )

    # --- Por faixa (linhas 15 a 18) ----------------------------------------
    _secao(ws, 14, "POR FAIXA DE PREÇO")
    _cabecalho_tabela(ws, 15, ["Faixa", "Quantidade", "% do total"])
    for i, faixa in enumerate(FAIXAS):
        linha = 16 + i
        fundo, texto, _ = CORES_FAIXA[faixa]
        c = ws.cell(row=linha, column=2, value=faixa)
        c.font = _fonte(bold=True, color=texto)
        c.fill = _preenchimento(fundo)
        ws.cell(row=linha, column=3, value=f"=COUNTIF(Itens!$H$2:$H${ultima},B{linha})").font = _fonte()
        pct = ws.cell(row=linha, column=4, value=f"=IF($C$6=0,0,C{linha}/$C$6)")
        pct.number_format = "0.0%"
        pct.font = _fonte()
        for col in (3, 4):
            ws.cell(row=linha, column=col).alignment = Alignment(horizontal="center")
        _linha_fina(ws, linha, 2, 4)

    # --- Por categoria (linha 21 em diante) -------------------------------
    _secao(ws, 20, "POR CATEGORIA (ordenado pelo preço médio)")
    _cabecalho_tabela(ws, 21, ["Categoria", "Quantidade", "Preço médio", "Menor", "Maior"])
    for i, cat in enumerate(resumo.por_categoria):
        linha = 22 + i
        grupo = cat.grupo.replace('"', '""')
        sub = cat.subcategoria.replace('"', '""')
        criterio = f'Itens!$D$2:$D${ultima},"{grupo}",Itens!$E$2:$E${ultima},"{sub}"'
        valores = [
            (cat.rotulo, None),
            (f"=COUNTIFS({criterio})", "0"),
            (f"=AVERAGEIFS({precos},{criterio})", formato_preco),
            (f"=_xlfn.MINIFS({precos},{criterio})", formato_preco),
            (f"=_xlfn.MAXIFS({precos},{criterio})", formato_preco),
        ]
        for col, (valor, formato) in enumerate(valores, start=2):
            c = ws.cell(row=linha, column=col, value=valor)
            c.font = _fonte()
            if formato:
                c.number_format = formato
                c.alignment = Alignment(horizontal="center")
        _linha_fina(ws, linha, 2, 6)
    ultima_categoria = 21 + len(resumo.por_categoria)

    # --- Gráficos ---------------------------------------------------------
    barras = BarChart()
    barras.type = "bar"
    barras.title = "Preço médio por categoria"
    barras.add_data(Reference(ws, min_col=4, min_row=21, max_row=ultima_categoria), titles_from_data=True)
    barras.set_categories(Reference(ws, min_col=2, min_row=22, max_row=ultima_categoria))
    barras.legend = None
    barras.x_axis.scaling.orientation = "maxMin"   # maior média no topo
    barras.x_axis.delete = False
    barras.y_axis.delete = False
    barras.y_axis.numFmt = "#,##0"
    barras.y_axis.majorGridlines = None
    barras.gapWidth = 60
    serie = barras.series[0]
    serie.graphicalProperties.solidFill = "7C5CFF"
    serie.graphicalProperties.line.noFill = True
    barras.height, barras.width = 8.5, 17
    ws.add_chart(barras, "H5")

    rosca = DoughnutChart(holeSize=55)
    rosca.title = "Produtos por faixa de preço"
    rosca.add_data(Reference(ws, min_col=3, min_row=15, max_row=18), titles_from_data=True)
    rosca.set_categories(Reference(ws, min_col=2, min_row=16, max_row=18))
    for i, faixa in enumerate(FAIXAS):
        ponto = DataPoint(idx=i)
        ponto.graphicalProperties.solidFill = CORES_FAIXA[faixa][2]
        ponto.graphicalProperties.line.solidFill = "FFFFFF"
        rosca.series[0].dPt.append(ponto)
    rosca.dataLabels = DataLabelList()
    rosca.dataLabels.showPercent = True
    rosca.dataLabels.showVal = False
    rosca.dataLabels.showCatName = False
    rosca.dataLabels.showSerName = False
    rosca.dataLabels.showLegendKey = False
    rosca.height, rosca.width = 8.5, 12
    ws.add_chart(rosca, "H23")


def montar_planilha(
    produtos: Iterable[Produto], caminho_saida: Path, gerado_em: datetime | None = None
) -> Path:
    produtos = sorted(produtos, key=lambda p: p.preco_valor, reverse=True)
    if not produtos:
        raise ValueError("Lista de produtos está vazia — nada para exportar.")

    resumo = resumir(produtos)
    formato_preco = f'"{resumo.moeda} "#,##0.00'
    ultima = len(produtos) + 1

    wb = Workbook()
    ws_resumo = wb.active
    ws_resumo.title = "Resumo"
    ws_itens = wb.create_sheet("Itens")

    _preencher_itens(ws_itens, produtos, ultima, formato_preco)
    _preencher_resumo(ws_resumo, resumo, ultima, formato_preco, gerado_em or datetime.now())

    wb.calculation.fullCalcOnLoad = True
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho_saida)
    return caminho_saida
