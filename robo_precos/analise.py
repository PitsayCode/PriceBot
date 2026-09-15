# -*- coding: utf-8 -*-
"""
analise.py
----------
Estatísticas e classificação de preços, usadas tanto pela interface quanto
pelo Excel (para que os dois mostrem exatamente os mesmos números).

Faixas de preço:
    Os limites são os percentis 33% e 66% dos preços coletados na execução.
    Até o 1º limite = Econômico; até o 2º = Intermediário; acima = Premium.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from .modelos import Produto

FAIXAS = ("Econômico", "Intermediário", "Premium")


@dataclass
class ResumoCategoria:
    grupo: str
    subcategoria: str
    quantidade: int
    media: float
    minimo: float
    maximo: float

    @property
    def rotulo(self) -> str:
        return f"{self.grupo} / {self.subcategoria}"


@dataclass
class Resumo:
    total: int
    moeda: str
    minimo: float
    maximo: float
    media: float
    mediana: float
    limites: tuple[float, float]
    por_faixa: dict[str, int]
    por_categoria: list[ResumoCategoria]
    mais_barato: Produto | None
    mais_caro: Produto | None


def limites_faixa(precos: Sequence[float]) -> tuple[float, float]:
    validos = sorted(p for p in precos if p > 0)
    if not validos:
        return 0.0, 0.0
    if len(validos) == 1:
        return validos[0], validos[0]
    economico, intermediario = statistics.quantiles(validos, n=3, method="inclusive")
    return round(economico, 2), round(intermediario, 2)


def classificar(valor: float, limites: tuple[float, float]) -> str:
    if valor <= limites[0]:
        return FAIXAS[0]
    if valor <= limites[1]:
        return FAIXAS[1]
    return FAIXAS[2]


def resumir(produtos: Iterable[Produto]) -> Resumo:
    produtos = list(produtos)
    if not produtos:
        return Resumo(0, "Rs.", 0.0, 0.0, 0.0, 0.0, (0.0, 0.0), dict.fromkeys(FAIXAS, 0), [], None, None)

    precos = [p.preco_valor for p in produtos]
    limites = limites_faixa(precos)

    por_faixa = dict.fromkeys(FAIXAS, 0)
    precos_por_categoria: dict[tuple[str, str], list[float]] = defaultdict(list)
    for p in produtos:
        por_faixa[classificar(p.preco_valor, limites)] += 1
        precos_por_categoria[(p.categoria_grupo, p.categoria_sub)].append(p.preco_valor)

    por_categoria = sorted(
        (
            ResumoCategoria(grupo, sub, len(v), statistics.fmean(v), min(v), max(v))
            for (grupo, sub), v in precos_por_categoria.items()
        ),
        key=lambda c: c.media,
        reverse=True,
    )

    return Resumo(
        total=len(produtos),
        moeda=Counter(p.moeda for p in produtos).most_common(1)[0][0],
        minimo=min(precos),
        maximo=max(precos),
        media=statistics.fmean(precos),
        mediana=statistics.median(precos),
        limites=limites,
        por_faixa=por_faixa,
        por_categoria=por_categoria,
        mais_barato=min(produtos, key=lambda p: p.preco_valor),
        mais_caro=max(produtos, key=lambda p: p.preco_valor),
    )


def formatar_preco(valor: float, moeda: str = "Rs.") -> str:
    """1500 -> 'Rs. 1.500' · 887.5 -> 'Rs. 887,50' (padrão brasileiro de separadores)."""
    texto = f"{valor:,.0f}" if abs(valor - round(valor)) < 0.005 else f"{valor:,.2f}"
    texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{moeda} {texto}"
