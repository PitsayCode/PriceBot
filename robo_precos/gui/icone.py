# -*- coding: utf-8 -*-
"""
icone.py
--------
Desenha o ícone do app (quadrado arredondado em degradê com um gráfico de
barras) em Python puro — sem Pillow — e salva como .ico/.png em assets/.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

from .. import config

_COR_A = (0x7C, 0x5C, 0xFF)
_COR_B = (0x22, 0xD3, 0xEE)
_BARRAS = ((0.30, 0.30), (0.50, 0.47), (0.70, 0.62))   # (centro x, altura) relativos


def _dist_retangulo(px: float, py: float, cx: float, cy: float, meia_l: float, meia_a: float, raio: float) -> float:
    """Distância com sinal até um retângulo arredondado (negativa = dentro)."""
    qx = abs(px - cx) - (meia_l - raio)
    qy = abs(py - cy) - (meia_a - raio)
    fora = math.hypot(max(qx, 0.0), max(qy, 0.0))
    dentro = min(max(qx, qy), 0.0)
    return fora + dentro - raio


def _cobertura(distancia: float) -> float:
    return min(1.0, max(0.0, 0.5 - distancia))


def _pixels(n: int) -> bytes:
    buf = bytearray(n * n * 4)
    meio = n / 2
    largura_barra = n * 0.13
    base = n * 0.77
    for y in range(n):
        py = y + 0.5
        for x in range(n):
            px = x + 0.5
            alfa = _cobertura(_dist_retangulo(px, py, meio, meio, meio, meio, n * 0.23))
            if alfa <= 0:
                continue
            t = (px + py) / (2 * n)
            cor = [a + (b - a) * t for a, b in zip(_COR_A, _COR_B)]
            barra = 0.0
            for bx, bh in _BARRAS:
                altura = n * bh
                d = _dist_retangulo(px, py, n * bx, base - altura / 2, largura_barra / 2, altura / 2, largura_barra * 0.35)
                barra = max(barra, _cobertura(d))
            barra *= 0.96
            cor = [c * (1 - barra) + 255 * barra for c in cor]
            i = (y * n + x) * 4
            buf[i:i + 4] = bytes((round(cor[0]), round(cor[1]), round(cor[2]), round(alfa * 255)))
    return bytes(buf)


def gerar_png(tamanho: int) -> bytes:
    n = max(8, int(tamanho))
    pixels = _pixels(n)
    linhas = b"".join(b"\x00" + pixels[y * n * 4:(y + 1) * n * 4] for y in range(n))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(linhas, 9))
        + bloco(b"IEND", b"")
    )


def _gerar_ico(tamanhos: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)) -> bytes:
    imagens = [gerar_png(t) for t in tamanhos]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    deslocamento = 6 + 16 * len(imagens)
    entradas = b""
    for tamanho, png in zip(tamanhos, imagens):
        lado = 0 if tamanho >= 256 else tamanho
        entradas += struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32, len(png), deslocamento)
        deslocamento += len(png)
    return cabecalho + entradas + b"".join(imagens)


def garantir_icone() -> Path | None:
    """Cria assets/icone.ico (uma vez) e devolve o caminho; None se não der."""
    caminho = config.PASTA_ASSETS / "icone.ico"
    try:
        if not caminho.exists():
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(_gerar_ico())
            (config.PASTA_ASSETS / "icone.png").write_bytes(gerar_png(512))
        return caminho
    except OSError:
        return None


if __name__ == "__main__":
    print(garantir_icone())
