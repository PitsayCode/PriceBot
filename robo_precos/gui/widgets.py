# -*- coding: utf-8 -*-
"""
widgets.py
----------
Componentes visuais do painel: cartões de indicador animados, gráfico de
barras, gráfico de rosca, tabela de produtos com busca/filtro e log ao vivo.
Os gráficos são desenhados direto num Canvas (sem matplotlib), o que deixa
o app leve e com animações suaves.
"""

from __future__ import annotations

import base64
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import ttk
from typing import Callable, Sequence

import customtkinter as ctk

from ..analise import FAIXAS, classificar, formatar_preco, limites_faixa
from ..modelos import Produto
from . import tema
from .icone import gerar_png


def _suavizar(t: float) -> float:
    return 1 - (1 - t) ** 3


class Animador:
    """Chama `passo(t)` com t indo de 0 a 1 (ease-out) ao longo de `duracao_ms`."""

    def __init__(self, widget: tk.Misc, passo: Callable[[float], None], duracao_ms: int = 650, quadros: int = 40):
        self._widget, self._passo = widget, passo
        self._intervalo = max(1, duracao_ms // quadros)
        self._quadros = quadros
        self._quadro = 0
        self._id: str | None = None

    def iniciar(self) -> None:
        if self._id:
            self._widget.after_cancel(self._id)
        self._quadro = 0
        self._tick()

    def _tick(self) -> None:
        self._quadro += 1
        t = min(1.0, self._quadro / self._quadros)
        self._passo(_suavizar(t))
        self._id = self._widget.after(self._intervalo, self._tick) if t < 1 else None


def _escala(widget: tk.Misc) -> float:
    return ctk.ScalingTracker.get_widget_scaling(widget)


def criar_logo(master: tk.Misc, tamanho: int, fundo: str) -> tk.Label:
    lado = round(tamanho * _escala(master))
    imagem = tk.PhotoImage(data=base64.b64encode(gerar_png(lado)))
    rotulo = tk.Label(master, image=imagem, bg=fundo, bd=0, highlightthickness=0)
    rotulo.image = imagem   # mantém a referência viva
    return rotulo


def _encurtar(fonte: tkfont.Font, texto: str, largura: float) -> str:
    if fonte.measure(texto) <= largura:
        return texto
    while texto and fonte.measure(texto + "…") > largura:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def retangulo_arredondado(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, **kw) -> int:
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pontos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pontos, smooth=True, **kw)


# ---------------------------------------------------------------------------
# Cartão de indicador
# ---------------------------------------------------------------------------
class CartaoIndicador(ctk.CTkFrame):
    def __init__(self, master, titulo: str, cor: str):
        super().__init__(master, fg_color=tema.CARTAO, corner_radius=14, border_width=1, border_color=tema.BORDA)
        self.grid_columnconfigure(1, weight=1)

        # height pequeno: a barra só estica até a altura do texto (o padrão do CTkFrame é 200px)
        ctk.CTkFrame(self, width=4, height=10, corner_radius=2, fg_color=cor).grid(
            row=0, column=0, rowspan=3, sticky="ns", padx=(16, 0), pady=16
        )
        ctk.CTkLabel(self, text=titulo.upper(), font=tema.fonte(11, "bold"), text_color=tema.TEXTO_SUAVE,
                     anchor="w").grid(row=0, column=1, sticky="ew", padx=14, pady=(14, 0))
        self._valor = ctk.CTkLabel(self, text="—", font=tema.fonte(26, "bold"), text_color=tema.TEXTO, anchor="w")
        self._valor.grid(row=1, column=1, sticky="ew", padx=14)
        self._sub = ctk.CTkLabel(self, text=" ", font=tema.fonte(12), text_color=tema.TEXTO_FRACO, anchor="w")
        self._sub.grid(row=2, column=1, sticky="ew", padx=14, pady=(0, 12))

        self._atual = self._origem = self._alvo = 0.0
        self._formato: Callable[[float], str] = str
        self._anim = Animador(self, self._passo, 800)

    def definir(self, valor: float | None, formato: Callable[[float], str], subtitulo: str = "") -> None:
        self._sub.configure(text=subtitulo or " ")
        if valor is None:
            self._atual = 0.0
            self._valor.configure(text="—")
            return
        self._origem, self._alvo, self._formato = self._atual, valor, formato
        self._anim.iniciar()

    def _passo(self, t: float) -> None:
        self._atual = self._origem + (self._alvo - self._origem) * t
        self._valor.configure(text=self._formato(self._alvo if t >= 1 else round(self._atual)))


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
class _PainelGrafico(ctk.CTkFrame):
    def __init__(self, master, titulo: str, subtitulo: str = "", altura: int = 170):
        super().__init__(master, fg_color=tema.CARTAO, corner_radius=14, border_width=1, border_color=tema.BORDA)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text=titulo, font=tema.fonte(15, "bold"), text_color=tema.TEXTO, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        self._subtitulo = ctk.CTkLabel(self, text=subtitulo, font=tema.fonte(12), text_color=tema.TEXTO_FRACO, anchor="w")
        self._subtitulo.grid(row=1, column=0, sticky="ew", padx=18)

        self.canvas = tk.Canvas(self, bg=tema.CARTAO, highlightthickness=0, bd=0,
                                height=round(altura * _escala(self)))
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=18, pady=(8, 16))
        self.canvas.bind("<Configure>", lambda _e: self._redesenhar())

        self._t = 1.0
        self._anim = Animador(self, self._animar, 900, 45)
        self._fontes: dict[tuple[int, bool], tkfont.Font] = {}

    def definir_subtitulo(self, texto: str) -> None:
        self._subtitulo.configure(text=texto)

    def _fonte(self, px: int, negrito: bool = False) -> tkfont.Font:
        chave = (px, negrito)
        if chave not in self._fontes:
            self._fontes[chave] = tkfont.Font(family=tema.FAMILIA, size=-round(px * _escala(self)),
                                              weight="bold" if negrito else "normal")
        return self._fontes[chave]

    def _animar(self, t: float) -> None:
        self._t = t
        self._redesenhar()

    def _redesenhar(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w > 40 and h > 40:
            self._desenhar(c, w, h, self._t)

    def _vazio(self, c: tk.Canvas, w: int, h: int) -> None:
        c.create_text(w / 2, h / 2, text="Sem dados ainda\nClique em “Iniciar coleta” ou “Modo demonstração”",
                      fill=tema.TEXTO_FRACO, font=self._fonte(13), justify="center")

    def _desenhar(self, c: tk.Canvas, w: int, h: int, t: float) -> None:
        raise NotImplementedError


class GraficoBarras(_PainelGrafico):
    MAX_BARRAS = 7

    def __init__(self, master, titulo: str, subtitulo: str = ""):
        super().__init__(master, titulo, subtitulo)
        self._itens: list[tuple[str, float]] = []
        self._formato: Callable[[float], str] = str

    def definir(self, itens: Sequence[tuple[str, float]], formato: Callable[[float], str]) -> None:
        self._itens, self._formato = list(itens)[: self.MAX_BARRAS], formato
        self._anim.iniciar()

    def _desenhar(self, c, w, h, t):
        if not self._itens:
            return self._vazio(c, w, h)
        s = _escala(self)
        f_rotulo, f_valor = self._fonte(12), self._fonte(12, True)
        larg_rotulo = min(max(f_rotulo.measure(r) for r, _ in self._itens) + 14 * s, w * 0.34)
        larg_valor = max(f_valor.measure(self._formato(v)) for _, v in self._itens) + 12 * s
        maximo = max(v for _, v in self._itens) or 1
        n = len(self._itens)
        linha = h / n
        espessura = min(linha * 0.58, 20 * s)
        x0, xmax = larg_rotulo, w - larg_valor

        for i, (rotulo, valor) in enumerate(self._itens):
            cy = linha * i + linha / 2
            c.create_text(0, cy, anchor="w", text=_encurtar(f_rotulo, rotulo, larg_rotulo - 14 * s),
                          fill=tema.TEXTO_SUAVE, font=f_rotulo)
            retangulo_arredondado(c, x0, cy - espessura / 2, xmax, cy + espessura / 2, espessura / 2,
                                  fill=tema.TRILHA, outline="")
            # atraso em cascata: cada barra começa um pouco depois da anterior
            ti = _suavizar(min(1.0, max(0.0, t * 1.4 - i * 0.4 / n)))
            x1 = x0 + max(espessura, (xmax - x0) * valor / maximo * ti)
            cor = tema.misturar(tema.PRIMARIA, tema.SECUNDARIA, i / max(n - 1, 1))
            retangulo_arredondado(c, x0, cy - espessura / 2, x1, cy + espessura / 2, espessura / 2,
                                  fill=cor, outline="")
            c.create_text(x1 + 8 * s, cy, anchor="w", text=self._formato(round(valor * ti)) if ti < 1 else self._formato(valor),
                          fill=tema.TEXTO, font=f_valor)


class GraficoRosca(_PainelGrafico):
    def __init__(self, master, titulo: str, subtitulo: str = ""):
        super().__init__(master, titulo, subtitulo)
        self._fatias: list[tuple[str, int, str]] = []

    def definir(self, fatias: Sequence[tuple[str, int, str]]) -> None:
        self._fatias = list(fatias)
        self._anim.iniciar()

    def _desenhar(self, c, w, h, t):
        total = sum(v for _, v, _ in self._fatias)
        if not total:
            return self._vazio(c, w, h)
        s = _escala(self)
        diametro = min(h - 4 * s, w * 0.44)
        espessura = max(10 * s, diametro * 0.15)
        x0, y0 = espessura / 2 + 2 * s, (h - diametro) / 2 + espessura / 2
        x1, y1 = x0 + diametro - espessura, y0 + diametro - espessura
        c.create_oval(x0, y0, x1, y1, outline=tema.TRILHA, width=espessura)

        inicio = 90.0
        for _, valor, cor in self._fatias:
            extensao = max(-359.9, -360 * valor / total * t)
            if abs(extensao) >= 0.5:
                c.create_arc(x0, y0, x1, y1, start=inicio, extent=extensao, style="arc", outline=cor, width=espessura)
            inicio += -360 * valor / total * t

        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        c.create_text(cx, cy - 8 * s, text=str(round(total * t)), fill=tema.TEXTO, font=self._fonte(22, True))
        c.create_text(cx, cy + 14 * s, text="produtos", fill=tema.TEXTO_FRACO, font=self._fonte(11))

        lx = x1 + espessura / 2 + 26 * s
        altura_linha = min(44 * s, h / len(self._fatias))
        topo = h / 2 - altura_linha * len(self._fatias) / 2
        f_nome, f_num, f_pct = self._fonte(13, True), self._fonte(20, True), self._fonte(12)
        for i, (nome, valor, cor) in enumerate(self._fatias):
            y = topo + altura_linha * i + altura_linha / 2
            c.create_oval(lx, y - 5 * s, lx + 10 * s, y + 5 * s, fill=cor, outline="")
            c.create_text(lx + 20 * s, y, anchor="w", text=nome, fill=tema.TEXTO_SUAVE, font=f_nome)
            c.create_text(w - 4 * s, y, anchor="e", text=f"{valor / total:.0%}", fill=tema.TEXTO_FRACO, font=f_pct)
            c.create_text(w - 4 * s - f_pct.measure("100%") - 14 * s, y, anchor="e",
                          text=str(round(valor * t)), fill=cor, font=f_num)


# ---------------------------------------------------------------------------
# Tabela de produtos
# ---------------------------------------------------------------------------
_ESTILO_CONFIGURADO = False


def _configurar_estilo_tabela(widget: tk.Misc) -> None:
    global _ESTILO_CONFIGURADO, _FONTES_TABELA
    if _ESTILO_CONFIGURADO:
        return
    estilo = ttk.Style(widget)
    estilo.theme_use("clam")
    # Tamanho negativo = pixels, na mesma escala das fontes do CustomTkinter.
    s = _escala(widget)
    fonte_linha = tkfont.Font(family=tema.FAMILIA, size=-round(13 * s))
    fonte_cabecalho = tkfont.Font(family=tema.FAMILIA, size=-round(12 * s), weight="bold")
    # Guarda as referências: se o objeto Font for coletado, o Tk apaga a fonte
    # e a tabela volta silenciosamente para a fonte padrão.
    _FONTES_TABELA = (fonte_linha, fonte_cabecalho)
    estilo.configure("PriceBot.Treeview", background=tema.FUNDO, fieldbackground=tema.FUNDO,
                     foreground=tema.TEXTO, borderwidth=0, font=fonte_linha,
                     rowheight=fonte_linha.metrics("linespace") + round(12 * s))
    estilo.map("PriceBot.Treeview", background=[("selected", tema.PRIMARIA)], foreground=[("selected", "#FFFFFF")])
    estilo.layout("PriceBot.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    estilo.configure("PriceBot.Treeview.Heading", background=tema.CARTAO_ALT, foreground=tema.TEXTO_SUAVE,
                     relief="flat", borderwidth=0, font=fonte_cabecalho, padding=(10, 8))
    estilo.map("PriceBot.Treeview.Heading", background=[("active", tema.CARTAO_HOVER)])
    _ESTILO_CONFIGURADO = True


class TabelaProdutos(ctk.CTkFrame):
    COLUNAS = (
        ("rank", "#", 54, "center"),
        ("nome", "Produto", 300, "w"),
        ("marca", "Marca", 150, "w"),
        ("categoria", "Categoria", 180, "w"),
        ("preco", "Preço", 110, "e"),
        ("faixa", "Faixa", 150, "w"),
    )
    SIMBOLOS = {"Econômico": "▼", "Intermediário": "◆", "Premium": "▲"}

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        barra.grid_columnconfigure(2, weight=1)

        self._busca = ctk.CTkEntry(barra, width=300, height=34, corner_radius=10, font=tema.fonte(13),
                                   placeholder_text="Buscar produto, marca ou categoria…",
                                   fg_color=tema.FUNDO, border_color=tema.BORDA, text_color=tema.TEXTO,
                                   placeholder_text_color=tema.TEXTO_FRACO)
        self._busca.grid(row=0, column=0, sticky="w")
        self._busca.bind("<KeyRelease>", lambda _e: self._atualizar())

        self._filtro = ctk.CTkSegmentedButton(
            barra, values=["Todas", *FAIXAS], command=lambda _v: self._atualizar(), height=34,
            font=tema.fonte(12), fg_color=tema.FUNDO, selected_color=tema.PRIMARIA,
            selected_hover_color=tema.PRIMARIA_HOVER, unselected_color=tema.FUNDO,
            unselected_hover_color=tema.CARTAO_HOVER, text_color=tema.TEXTO)
        self._filtro.set("Todas")
        self._filtro.grid(row=0, column=1, padx=12)

        self._contagem = ctk.CTkLabel(barra, text="Nenhum produto ainda", font=tema.fonte(12), text_color=tema.TEXTO_SUAVE)
        self._contagem.grid(row=0, column=3, sticky="e")

        moldura = ctk.CTkFrame(self, fg_color=tema.FUNDO, corner_radius=10)
        moldura.grid(row=1, column=0, sticky="nsew")
        moldura.grid_columnconfigure(0, weight=1)
        moldura.grid_rowconfigure(0, weight=1)

        _configurar_estilo_tabela(self)
        self.tree = ttk.Treeview(moldura, columns=[c[0] for c in self.COLUNAS], show="headings",
                                 style="PriceBot.Treeview", selectmode="browse")
        s = _escala(self)
        for chave, titulo, largura, ancora in self.COLUNAS:
            self.tree.heading(chave, text=titulo, anchor=ancora, command=lambda k=chave: self._ordenar_por(k))
            self.tree.column(chave, width=round(largura * s), minwidth=round(40 * s), anchor=ancora,
                             stretch=chave in ("nome", "categoria"))
        self.tree.tag_configure("par", background=tema.FUNDO)
        self.tree.tag_configure("impar", background=tema.CARTAO_ALT)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)

        rolagem = ctk.CTkScrollbar(moldura, command=self.tree.yview, button_color=tema.BORDA,
                                   button_hover_color=tema.TEXTO_FRACO)
        rolagem.grid(row=0, column=1, sticky="ns", padx=(2, 4), pady=6)
        self.tree.configure(yscrollcommand=rolagem.set)

        self._produtos: list[Produto] = []
        self._limites = (0.0, 0.0)
        self._ranks: dict[str, int] = {}
        self._ordem = ("rank", False)
        self._id_insercao: str | None = None

    def definir(self, produtos: Sequence[Produto], animar: bool = True) -> None:
        self._produtos = list(produtos)
        self._limites = limites_faixa([p.preco_valor for p in self._produtos])
        precos = sorted((p.preco_valor for p in self._produtos), reverse=True)
        self._ranks = {p.id_produto: precos.index(p.preco_valor) + 1 for p in self._produtos}
        self._atualizar(animar)

    def _chave(self, item: tuple[Produto, str]):
        p, faixa = item
        coluna = self._ordem[0]
        return {
            "rank": lambda: self._ranks[p.id_produto],
            "nome": lambda: p.nome.lower(),
            "marca": lambda: p.marca.lower(),
            "categoria": lambda: p.categoria.lower(),
            "preco": lambda: p.preco_valor,
            "faixa": lambda: FAIXAS.index(faixa),
        }[coluna]()

    def _ordenar_por(self, coluna: str) -> None:
        atual, desc = self._ordem
        self._ordem = (coluna, not desc) if coluna == atual else (coluna, coluna == "preco")
        self._atualizar()

    def _atualizar(self, animar: bool = False) -> None:
        if self._id_insercao:
            self.after_cancel(self._id_insercao)
            self._id_insercao = None
        self.tree.delete(*self.tree.get_children())

        termo = self._busca.get().strip().lower()
        filtro = self._filtro.get()
        linhas = []
        for p in self._produtos:
            faixa = classificar(p.preco_valor, self._limites)
            if filtro != "Todas" and faixa != filtro:
                continue
            if termo and termo not in f"{p.nome} {p.marca} {p.categoria}".lower():
                continue
            linhas.append((p, faixa))
        linhas.sort(key=self._chave, reverse=self._ordem[1])

        for chave, titulo, _, _ in self.COLUNAS:
            seta = (" ▼" if self._ordem[1] else " ▲") if chave == self._ordem[0] else ""
            self.tree.heading(chave, text=titulo + seta)

        self._contagem.configure(
            text=f"{len(linhas)} de {len(self._produtos)} produtos" if self._produtos else "Nenhum produto ainda"
        )
        self._inserir(linhas, 0, lote=2 if animar else len(linhas) or 1)

    def _inserir(self, linhas: list[tuple[Produto, str]], inicio: int, lote: int) -> None:
        for i in range(inicio, min(inicio + lote, len(linhas))):
            p, faixa = linhas[i]
            self.tree.insert("", "end", tags=("par" if i % 2 == 0 else "impar",), values=(
                self._ranks[p.id_produto], p.nome, p.marca, p.categoria,
                formatar_preco(p.preco_valor, p.moeda), f"{self.SIMBOLOS[faixa]}  {faixa}",
            ))
        proximo = inicio + lote
        self._id_insercao = (
            self.after(22, lambda: self._inserir(linhas, proximo, lote)) if proximo < len(linhas) else None
        )


# ---------------------------------------------------------------------------
# Log em tempo real
# ---------------------------------------------------------------------------
class PainelLog(ctk.CTkFrame):
    NIVEIS = {
        "info": ("·", tema.TEXTO_SUAVE),
        "ok": ("✓", tema.SUCESSO),
        "aviso": ("!", tema.AVISO),
        "erro": ("✗", tema.ERRO),
    }

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.caixa = ctk.CTkTextbox(self, fg_color=tema.FUNDO, corner_radius=10, border_width=0,
                                    font=ctk.CTkFont(family=tema.FAMILIA_MONO, size=13),
                                    text_color=tema.TEXTO, wrap="word", activate_scrollbars=True)
        self.caixa.pack(fill="both", expand=True)
        for nivel, (_, cor) in self.NIVEIS.items():
            self.caixa.tag_config(nivel, foreground=cor)
        self.caixa.tag_config("hora", foreground=tema.TEXTO_FRACO)
        self.caixa.configure(state="disabled")

    def adicionar(self, horario: datetime, mensagem: str, nivel: str = "info") -> None:
        simbolo = self.NIVEIS.get(nivel, self.NIVEIS["info"])[0]
        self.caixa.configure(state="normal")
        self.caixa.insert("end", f" {horario:%H:%M:%S}  ", "hora")
        self.caixa.insert("end", f"{simbolo}  {mensagem}\n", nivel)
        self.caixa.configure(state="disabled")
        self.caixa.see("end")

    def limpar(self) -> None:
        self.caixa.configure(state="normal")
        self.caixa.delete("1.0", "end")
        self.caixa.configure(state="disabled")
