# -*- coding: utf-8 -*-
"""
relator.py
----------
Canal de comunicação entre o robô e quem o executa.

O robô nunca usa print() direto: ele chama relator.log(), relator.progresso()
e relator.checar_cancelamento(). Na linha de comando isso vira texto no
console; na interface gráfica vira eventos numa fila, consumidos pela tela.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


class Cancelado(Exception):
    """Lançada quando o usuário pede para parar a execução."""


@dataclass
class Evento:
    tipo: str                      # "log" | "progresso" | "produtos" | "concluido" | "erro" | "cancelado"
    dados: dict = field(default_factory=dict)
    horario: datetime = field(default_factory=datetime.now)


def _imprimir_no_console(evento: Evento) -> None:
    if evento.tipo == "log":
        prefixo = {"info": "  ", "ok": "✓ ", "aviso": "! ", "erro": "✗ "}.get(
            evento.dados.get("nivel", "info"), "  "
        )
        print(f"[{evento.horario:%H:%M:%S}] {prefixo}{evento.dados['mensagem']}")
    elif evento.tipo == "progresso":
        pct = int(evento.dados["fracao"] * 100)
        print(f"[{evento.horario:%H:%M:%S}] ── {pct:3d}% · {evento.dados['etapa']}")


class Relator:
    def __init__(
        self,
        ao_evento: Callable[[Evento], None] | None = None,
        cancelar: threading.Event | None = None,
    ) -> None:
        self._ao_evento = ao_evento or _imprimir_no_console
        self._cancelar = cancelar or threading.Event()

    def evento(self, tipo: str, **dados) -> None:
        self._ao_evento(Evento(tipo, dados))

    def log(self, mensagem: str, nivel: str = "info") -> None:
        self.evento("log", mensagem=mensagem, nivel=nivel)

    def progresso(self, fracao: float, etapa: str) -> None:
        self.evento("progresso", fracao=max(0.0, min(1.0, fracao)), etapa=etapa)

    def checar_cancelamento(self) -> None:
        if self._cancelar.is_set():
            raise Cancelado("Execução interrompida pelo usuário.")
