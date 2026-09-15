# -*- coding: utf-8 -*-
"""
modelos.py
----------
Estruturas de dados compartilhadas entre scraper, análise, Excel e interface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class Produto:
    id_produto: str
    nome: str
    preco_valor: float
    moeda: str = "Rs."
    preco_texto: str = ""
    marca: str = "Não identificada"
    categoria_grupo: str = "Não classificado"
    categoria_sub: str = "Não classificado"
    url: str = ""

    @property
    def categoria(self) -> str:
        return f"{self.categoria_grupo} / {self.categoria_sub}"

    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict) -> "Produto":
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dados.items() if k in nomes})
