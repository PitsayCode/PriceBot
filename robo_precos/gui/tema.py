# -*- coding: utf-8 -*-
"""
tema.py
-------
Paleta e tipografia da interface. Troque as cores aqui para adaptar à
identidade visual do seu perfil.
"""

from __future__ import annotations

import customtkinter as ctk

FUNDO = "#0B1020"
LATERAL = "#0E1528"
CARTAO = "#141C31"
CARTAO_ALT = "#111830"
CARTAO_HOVER = "#1C2644"
BORDA = "#232E4D"
TRILHA = "#1E2742"

TEXTO = "#E8ECF5"
TEXTO_SUAVE = "#8B95B0"
TEXTO_FRACO = "#5B6582"

PRIMARIA = "#7C5CFF"
PRIMARIA_HOVER = "#6846F5"
SECUNDARIA = "#22D3EE"
SUCESSO = "#34D399"
AVISO = "#FBBF24"
ERRO = "#F87171"
ROSA = "#F472B6"

CORES_FAIXA = {
    "Econômico": SUCESSO,
    "Intermediário": AVISO,
    "Premium": ROSA,
}

FAMILIA = "Segoe UI"
FAMILIA_MONO = "Consolas"


def fonte(tamanho: int = 13, peso: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILIA, size=tamanho, weight=peso)


def misturar(cor_a: str, cor_b: str, t: float) -> str:
    """Interpola duas cores hex: t=0 -> cor_a, t=1 -> cor_b."""
    a = [int(cor_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(cor_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
