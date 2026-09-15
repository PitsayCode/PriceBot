# -*- coding: utf-8 -*-
"""
gui/app.py
----------
Janela principal do PriceBot.

O robô roda numa thread separada e conversa com a tela por uma fila de
eventos (ver relator.py) — a interface nunca congela durante a coleta e
o botão "Parar" interrompe com segurança entre uma página e outra.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .. import __version__, config, pipeline
from ..analise import FAIXAS, formatar_preco, resumir
from ..cofre import Cofre, Conta, mascarar_email
from ..modelos import Produto
from ..relator import Cancelado, Evento, Relator
from . import tema
from .dialogos import DialogoCofre, DialogoCriarCofre, DialogoDesbloquear
from .icone import garantir_icone
from .widgets import CartaoIndicador, GraficoBarras, GraficoRosca, PainelLog, TabelaProdutos, criar_logo

ESTADOS = {
    "pronto": ("Pronto", tema.TEXTO_SUAVE),
    "rodando": ("Executando", tema.SECUNDARIA),
    "concluido": ("Concluído", tema.SUCESSO),
    "erro": ("Erro", tema.ERRO),
    "cancelado": ("Interrompido", tema.AVISO),
}


def _abrir_no_sistema(caminho: Path) -> None:
    if sys.platform == "win32":
        os.startfile(caminho)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho)])


def _encurtar(texto: str, limite: int = 30) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


class AplicativoPriceBot(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=tema.FUNDO)
        self.title(f"{config.APP_NOME} — {config.APP_SUBTITULO}")
        self._posicionar_janela()
        self._aplicar_icone()

        self._fila: queue.Queue[Evento] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._cancelar = threading.Event()
        self._progresso_alvo = self._progresso_atual = 0.0
        self._ultimo_excel: Path | None = None
        self._id_fila: str | None = None
        self._cofre: Cofre | None = None       # chaves só na memória, enquanto desbloqueado
        self._conta_id: str | None = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._montar_lateral()
        self._montar_conteudo()

        self._definir_estado("pronto")
        self._atualizar_conta()
        self._carregar_ultima_coleta()

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self._processar_fila()

    # ------------------------------------------------------------------ janela
    def _posicionar_janela(self) -> None:
        escala = self._get_window_scaling()
        tela_l, tela_a = self.winfo_screenwidth(), self.winfo_screenheight()
        largura = min(1380, int(tela_l * 0.92 / escala))
        altura = min(880, int(tela_a * 0.86 / escala))
        x = max(0, int((tela_l - largura * escala) / 2))
        y = max(0, int((tela_a - altura * escala) / 2) - 20)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self.minsize(min(1120, largura), min(700, altura))

    def _aplicar_icone(self) -> None:
        icone = garantir_icone()
        if icone and sys.platform == "win32":
            self.iconbitmap(str(icone))

    # ----------------------------------------------------------------- lateral
    def _montar_lateral(self) -> None:
        lateral = ctk.CTkFrame(self, width=268, corner_radius=0, fg_color=tema.LATERAL)
        lateral.grid(row=0, column=0, sticky="nsw")
        lateral.grid_propagate(False)
        lateral.grid_columnconfigure(0, weight=1)

        marca = ctk.CTkFrame(lateral, fg_color="transparent")
        marca.grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 26))
        criar_logo(marca, 44, tema.LATERAL).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(marca, text=config.APP_NOME, font=tema.fonte(21, "bold"), text_color=tema.TEXTO,
                     anchor="w").grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(marca, text=config.APP_SUBTITULO, font=tema.fonte(12), text_color=tema.TEXTO_SUAVE,
                     anchor="w").grid(row=1, column=1, sticky="nw")

        self.bt_iniciar = ctk.CTkButton(
            lateral, text="▶   Iniciar coleta", height=48, corner_radius=12, font=tema.fonte(15, "bold"),
            fg_color=tema.PRIMARIA, hover_color=tema.PRIMARIA_HOVER, text_color="#FFFFFF",
            text_color_disabled=tema.misturar("#FFFFFF", tema.PRIMARIA, 0.5), command=self._iniciar_coleta)
        self.bt_iniciar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.bt_demo = ctk.CTkButton(
            lateral, text="✦   Modo demonstração", height=42, corner_radius=12, font=tema.fonte(13, "bold"),
            fg_color="transparent", border_width=1, border_color=tema.BORDA, hover_color=tema.CARTAO_HOVER,
            text_color=tema.TEXTO, text_color_disabled=tema.TEXTO_FRACO, command=self._iniciar_demo)
        self.bt_demo.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.bt_parar = ctk.CTkButton(
            lateral, text="■   Parar", height=42, corner_radius=12, font=tema.fonte(13, "bold"),
            fg_color="transparent", border_width=1, border_color=tema.misturar(tema.ERRO, tema.LATERAL, 0.55),
            hover_color=tema.misturar(tema.ERRO, tema.LATERAL, 0.85), text_color=tema.ERRO,
            text_color_disabled=tema.TEXTO_FRACO, command=self._parar)
        self.bt_parar.grid(row=3, column=0, sticky="ew", padx=20)

        self._secao(lateral, 4, "CONFIGURAÇÕES")
        self.sw_login = self._switch(lateral, 5, "Fazer login no site")
        self.sw_navegador = self._switch(lateral, 6, "Mostrar o navegador")
        if Cofre.existe():
            self.sw_login.select()
        self.bt_cofre = self._botao_menu(lateral, 7, "⚿   Cofre de contas", self._abrir_cofre)
        self.lb_conta = ctk.CTkLabel(lateral, text="", font=tema.fonte(11), text_color=tema.TEXTO_FRACO, anchor="w")
        self.lb_conta.grid(row=8, column=0, sticky="ew", padx=34)
        self.bt_bloquear = ctk.CTkButton(
            lateral, text="Bloquear cofre", width=0, height=22, anchor="w", font=tema.fonte(11, "bold"),
            fg_color="transparent", hover_color=tema.CARTAO_HOVER, text_color=tema.SECUNDARIA,
            text_color_disabled=tema.TEXTO_FRACO, command=self._bloquear_cofre)
        self.bt_bloquear.grid(row=9, column=0, sticky="w", padx=26)

        self._secao(lateral, 10, "RESULTADOS")
        self._botao_menu(lateral, 11, "▤   Abrir último Excel", self._abrir_excel)
        self._botao_menu(lateral, 12, "❐   Abrir pasta de saída", self._abrir_pasta)

        lateral.grid_rowconfigure(20, weight=1)
        ctk.CTkFrame(lateral, height=1, fg_color=tema.BORDA).grid(row=21, column=0, sticky="ew", padx=20)
        ctk.CTkLabel(lateral, text=config.ASSINATURA_RODAPE, font=tema.fonte(12, "bold"),
                     text_color=tema.TEXTO_SUAVE, anchor="w").grid(row=22, column=0, sticky="ew", padx=22, pady=(14, 0))
        ctk.CTkLabel(lateral, text=f"v{__version__} · Python + Playwright", font=tema.fonte(11),
                     text_color=tema.TEXTO_FRACO, anchor="w").grid(row=23, column=0, sticky="ew", padx=22, pady=(0, 20))

    def _secao(self, master, linha: int, texto: str) -> None:
        ctk.CTkLabel(master, text=texto, font=tema.fonte(11, "bold"), text_color=tema.TEXTO_FRACO,
                     anchor="w").grid(row=linha, column=0, sticky="ew", padx=24, pady=(28, 8))

    def _switch(self, master, linha: int, texto: str) -> ctk.CTkSwitch:
        switch = ctk.CTkSwitch(master, text=texto, font=tema.fonte(13), text_color=tema.TEXTO,
                               progress_color=tema.PRIMARIA, fg_color=tema.TRILHA, button_color="#FFFFFF",
                               button_hover_color="#E5E7EB", text_color_disabled=tema.TEXTO_FRACO)
        switch.grid(row=linha, column=0, sticky="w", padx=24, pady=6)
        return switch

    def _botao_menu(self, master, linha: int, texto: str, comando) -> ctk.CTkButton:
        botao = ctk.CTkButton(master, text=texto, anchor="w", height=38, corner_radius=10, font=tema.fonte(13),
                              fg_color="transparent", hover_color=tema.CARTAO_HOVER, text_color=tema.TEXTO,
                              text_color_disabled=tema.TEXTO_FRACO, command=comando)
        botao.grid(row=linha, column=0, sticky="ew", padx=14, pady=1)
        return botao

    # ---------------------------------------------------------------- conteúdo
    def _montar_conteudo(self) -> None:
        area = ctk.CTkFrame(self, fg_color="transparent")
        area.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(4, weight=1)

        cabecalho = ctk.CTkFrame(area, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew")
        cabecalho.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cabecalho, text="Painel de preços", font=tema.fonte(28, "bold"), text_color=tema.TEXTO,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.lb_subtitulo = ctk.CTkLabel(cabecalho, text="automationexercise.com  ·  nenhuma coleta ainda",
                                         font=tema.fonte(13), text_color=tema.TEXTO_SUAVE, anchor="w")
        self.lb_subtitulo.grid(row=1, column=0, sticky="w")
        self.lb_status = ctk.CTkLabel(cabecalho, text="", height=32, corner_radius=16, font=tema.fonte(12, "bold"))
        self.lb_status.grid(row=0, column=1, rowspan=2, sticky="e")

        progresso = ctk.CTkFrame(area, fg_color=tema.CARTAO, corner_radius=14, border_width=1, border_color=tema.BORDA)
        progresso.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        progresso.grid_columnconfigure(0, weight=1)
        self.lb_etapa = ctk.CTkLabel(progresso, text="Aguardando — escolha “Iniciar coleta” ou “Modo demonstração”",
                                     font=tema.fonte(13), text_color=tema.TEXTO_SUAVE, anchor="w")
        self.lb_etapa.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 6))
        self.lb_pct = ctk.CTkLabel(progresso, text="0%", font=tema.fonte(13, "bold"), text_color=tema.TEXTO)
        self.lb_pct.grid(row=0, column=1, sticky="e", padx=18, pady=(12, 6))
        self.barra = ctk.CTkProgressBar(progresso, height=8, corner_radius=4, progress_color=tema.PRIMARIA,
                                        fg_color=tema.TRILHA)
        self.barra.set(0)
        self.barra.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 16))

        cartoes = ctk.CTkFrame(area, fg_color="transparent")
        cartoes.grid(row=2, column=0, sticky="ew")
        self.card_total = CartaoIndicador(cartoes, "Produtos", tema.PRIMARIA)
        self.card_menor = CartaoIndicador(cartoes, "Menor preço", tema.SUCESSO)
        self.card_media = CartaoIndicador(cartoes, "Preço médio", tema.SECUNDARIA)
        self.card_maior = CartaoIndicador(cartoes, "Maior preço", tema.ROSA)
        for i, cartao in enumerate((self.card_total, self.card_menor, self.card_media, self.card_maior)):
            cartoes.grid_columnconfigure(i, weight=1, uniform="cartoes")
            cartao.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 7, 0 if i == 3 else 7))

        graficos = ctk.CTkFrame(area, fg_color="transparent")
        graficos.grid(row=3, column=0, sticky="ew", pady=14)
        graficos.grid_columnconfigure(0, weight=3, uniform="graficos")
        graficos.grid_columnconfigure(1, weight=2, uniform="graficos")
        self.gr_barras = GraficoBarras(graficos, "Preço médio por categoria", "Categorias com maior ticket médio")
        self.gr_barras.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.gr_rosca = GraficoRosca(graficos, "Distribuição por faixa", "Percentis 33% e 66% dos preços")
        self.gr_rosca.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        self.abas = ctk.CTkTabview(
            area, fg_color=tema.CARTAO, corner_radius=14, border_width=1, border_color=tema.BORDA, anchor="w",
            segmented_button_fg_color=tema.LATERAL, segmented_button_selected_color=tema.PRIMARIA,
            segmented_button_selected_hover_color=tema.PRIMARIA_HOVER,
            segmented_button_unselected_color=tema.LATERAL,
            segmented_button_unselected_hover_color=tema.CARTAO_HOVER, text_color=tema.TEXTO)
        self.abas.grid(row=4, column=0, sticky="nsew")
        self.tabela = TabelaProdutos(self.abas.add("Produtos"))
        self.tabela.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = PainelLog(self.abas.add("Log ao vivo"))
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ------------------------------------------------------------------ estado
    def _definir_estado(self, estado: str) -> None:
        texto, cor = ESTADOS[estado]
        self.lb_status.configure(text=f"   ●  {texto}   ", text_color=cor,
                                 fg_color=tema.misturar(cor, tema.FUNDO, 0.84))
        rodando = estado == "rodando"
        normal, desativado = "normal", "disabled"
        for widget in (self.bt_iniciar, self.bt_demo, self.sw_login, self.sw_navegador, self.bt_cofre,
                       self.bt_bloquear):
            widget.configure(state=desativado if rodando else normal)
        self.bt_parar.configure(state=normal if rodando else desativado)
        self.barra.configure(progress_color={"erro": tema.ERRO, "cancelado": tema.AVISO,
                                             "concluido": tema.SUCESSO}.get(estado, tema.PRIMARIA))

    def _atualizar_conta(self) -> None:
        if self._cofre and self._cofre.desbloqueado:
            conta = self._conta_selecionada()
            rotulo = (conta.apelido or mascarar_email(conta.email)) if conta else "escolha uma conta"
            self.lb_conta.configure(text=_encurtar(f"◉ Aberto · {rotulo}", 34), text_color=tema.SUCESSO)
            self.bt_bloquear.grid()
        else:
            quantidade = Cofre.quantidade()
            texto = (f"● Bloqueado · {quantidade} conta{'s' if quantidade != 1 else ''}"
                     if Cofre.existe() else "Nenhum cofre criado")
            self.lb_conta.configure(text=texto, text_color=tema.TEXTO_FRACO)
            self.bt_bloquear.grid_remove()

    def _conta_selecionada(self) -> Conta | None:
        if not (self._cofre and self._cofre.desbloqueado and self._conta_id):
            return None
        try:
            return self._cofre.obter(self._conta_id)
        except (KeyError, ValueError):
            self._conta_id = None
            return None

    def _texto_subtitulo(self, resultado: pipeline.ResultadoExecucao) -> str:
        partes = [
            "automationexercise.com",
            f"coleta de {resultado.gerado_em:%d/%m/%Y às %H:%M}",
            f"{len(resultado.produtos)} produtos",
            f"{resultado.duracao_s:.1f}s",
        ]
        if resultado.demonstracao:
            partes.append("dados de demonstração")
        return "  ·  ".join(partes)

    # --------------------------------------------------------------- execuções
    def _iniciar_coleta(self) -> None:
        autenticar = bool(self.sw_login.get())
        cofre, conta_id = None, None
        if autenticar:
            cofre = self._garantir_cofre()
            if cofre is None:
                return
            conta = self._conta_selecionada() or self._escolher_conta(cofre)
            if conta is None:
                return
            conta_id = conta.id
        opcoes = pipeline.OpcoesExecucao(autenticar=autenticar, headless=not self.sw_navegador.get(),
                                         cofre=cofre, conta_id=conta_id)
        self._rodar(lambda relator: pipeline.executar(opcoes, relator))

    def _iniciar_demo(self) -> None:
        self._rodar(pipeline.executar_demo)

    def _garantir_cofre(self) -> Cofre | None:
        """Devolve o cofre desbloqueado — pede a senha-mestra (ou cria o cofre) se preciso."""
        if self._cofre and self._cofre.desbloqueado:
            return self._cofre
        dialogo = DialogoDesbloquear(self) if Cofre.existe() else DialogoCriarCofre(self)
        cofre = dialogo.mostrar()
        if cofre:
            self._cofre = cofre
            self.log.adicionar(datetime.now(), "Cofre de contas desbloqueado (chaves só na memória).", "ok")
        self._atualizar_conta()
        return cofre

    def _escolher_conta(self, cofre: Cofre) -> Conta | None:
        conta_id = DialogoCofre(self, cofre, self._conta_id).mostrar()
        if conta_id:
            self._conta_id = conta_id
        conta = self._conta_selecionada() if conta_id else None
        self._atualizar_conta()
        return conta

    def _abrir_cofre(self) -> None:
        cofre = self._garantir_cofre()
        if cofre and self._escolher_conta(cofre):
            self.sw_login.select()

    def _bloquear_cofre(self) -> None:
        if self._cofre:
            self._cofre.bloquear()
        self._cofre = None
        self.log.adicionar(datetime.now(), "Cofre bloqueado — chaves removidas da memória.", "info")
        self._atualizar_conta()

    def _rodar(self, tarefa) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._cancelar = threading.Event()
        relator = Relator(self._fila.put, self._cancelar)

        self.log.limpar()
        self.abas.set("Log ao vivo")
        self._progresso_alvo = self._progresso_atual = 0.0
        self.barra.set(0)
        self.lb_pct.configure(text="0%")
        self.lb_etapa.configure(text="Preparando…", text_color=tema.TEXTO)
        self._definir_estado("rodando")

        def alvo() -> None:
            try:
                resultado = tarefa(relator)
            except Cancelado:
                relator.log("Execução interrompida pelo usuário.", "aviso")
                relator.evento("cancelado")
            except Exception as exc:  # noqa: BLE001 — qualquer falha vai para a tela
                self._registrar_erro()
                mensagem = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
                relator.log(mensagem, "erro")
                relator.evento("erro", mensagem=mensagem)
            else:
                relator.evento("concluido", resultado=resultado)

        self._thread = threading.Thread(target=alvo, name="robo-precos", daemon=True)
        self._thread.start()

    def _parar(self) -> None:
        self._cancelar.set()
        self.bt_parar.configure(state="disabled")
        self.lb_etapa.configure(text="Parando com segurança…", text_color=tema.AVISO)

    @staticmethod
    def _registrar_erro() -> None:
        try:
            config.PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
            with (config.PASTA_SAIDA / "erros.log").open("a", encoding="utf-8") as arquivo:
                arquivo.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} =====\n{traceback.format_exc()}")
        except OSError:
            pass

    # ------------------------------------------------------------------ eventos
    def _processar_fila(self) -> None:
        try:
            while True:
                self._tratar_evento(self._fila.get_nowait())
        except queue.Empty:
            pass

        diferenca = self._progresso_alvo - self._progresso_atual
        if abs(diferenca) > 0.0005:
            self._progresso_atual += diferenca * 0.16 if abs(diferenca) > 0.002 else diferenca
            self.barra.set(self._progresso_atual)
            self.lb_pct.configure(text=f"{self._progresso_atual:.0%}")
        self._id_fila = self.after(30, self._processar_fila)

    def _tratar_evento(self, evento: Evento) -> None:
        dados = evento.dados
        if evento.tipo == "log":
            self.log.adicionar(evento.horario, dados["mensagem"], dados.get("nivel", "info"))
        elif evento.tipo == "progresso":
            self._progresso_alvo = dados["fracao"]
            self.lb_etapa.configure(text=dados["etapa"], text_color=tema.TEXTO)
        elif evento.tipo == "produtos":
            self.abas.set("Produtos")
            self._exibir_produtos(dados["produtos"])
        elif evento.tipo == "concluido":
            resultado: pipeline.ResultadoExecucao = dados["resultado"]
            self._ultimo_excel = resultado.caminho_excel
            self._progresso_alvo = 1.0
            self.lb_subtitulo.configure(text=self._texto_subtitulo(resultado))
            self.lb_etapa.configure(text=f"Concluído em {resultado.duracao_s:.1f}s  ·  Excel: {resultado.caminho_excel.name}",
                                    text_color=tema.SUCESSO)
            self._definir_estado("concluido")
        elif evento.tipo == "erro":
            self.abas.set("Log ao vivo")
            self.lb_etapa.configure(text=f"Falhou: {dados['mensagem']}", text_color=tema.ERRO)
            self._definir_estado("erro")
        elif evento.tipo == "cancelado":
            self.lb_etapa.configure(text="Execução interrompida pelo usuário", text_color=tema.AVISO)
            self._definir_estado("cancelado")

    def _exibir_produtos(self, produtos: list[Produto]) -> None:
        resumo = resumir(produtos)

        def preco(valor: float) -> str:
            return formatar_preco(valor, resumo.moeda)

        marcas = {p.marca for p in produtos if p.marca != "Não identificada"}
        self.card_total.definir(resumo.total, lambda v: f"{v:.0f}",
                                f"{len(resumo.por_categoria)} categorias · {len(marcas)} marcas")
        self.card_menor.definir(resumo.minimo, preco, _encurtar(resumo.mais_barato.nome) if resumo.mais_barato else "")
        self.card_media.definir(resumo.media, preco, f"Mediana {preco(resumo.mediana)}")
        self.card_maior.definir(resumo.maximo, preco, _encurtar(resumo.mais_caro.nome) if resumo.mais_caro else "")

        self.gr_barras.definir([(c.rotulo, c.media) for c in resumo.por_categoria], preco)
        self.gr_rosca.definir([(f, resumo.por_faixa[f], tema.CORES_FAIXA[f]) for f in FAIXAS])
        economico, intermediario = resumo.limites
        self.gr_rosca.definir_subtitulo(f"Econômico até {preco(economico)} · Intermediário até {preco(intermediario)}")
        self.tabela.definir(produtos, animar=True)

    def _carregar_ultima_coleta(self) -> None:
        resultado = pipeline.carregar_ultima_coleta()
        if not resultado:
            return
        self._ultimo_excel = resultado.caminho_excel
        self.lb_subtitulo.configure(text=self._texto_subtitulo(resultado))
        self.log.adicionar(datetime.now(), f"Última coleta carregada ({resultado.gerado_em:%d/%m/%Y %H:%M}).", "info")
        self.after(300, lambda: self._exibir_produtos(resultado.produtos))

    # ------------------------------------------------------------- resultados
    def _abrir_excel(self) -> None:
        caminho = self._ultimo_excel if self._ultimo_excel and self._ultimo_excel.exists() else None
        if caminho is None and config.PASTA_SAIDA.exists():
            planilhas = sorted(config.PASTA_SAIDA.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
            caminho = planilhas[0] if planilhas else None
        if caminho is None:
            messagebox.showinfo(config.APP_NOME, "Nenhum Excel gerado ainda. Rode uma coleta primeiro.", parent=self)
            return
        _abrir_no_sistema(caminho)

    def _abrir_pasta(self) -> None:
        config.PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        _abrir_no_sistema(config.PASTA_SAIDA)

    # ------------------------------------------------------------- encerramento
    def _ao_fechar(self) -> None:
        if not (self._thread and self._thread.is_alive()):
            self.destroy()
            return
        if messagebox.askyesno(config.APP_NOME, "O robô ainda está rodando. Parar e fechar?", parent=self):
            self._parar()
            self._fechar_quando_parar(0)

    def _fechar_quando_parar(self, tentativas: int) -> None:
        if self._thread and self._thread.is_alive() and tentativas < 150:
            self.after(100, lambda: self._fechar_quando_parar(tentativas + 1))
        else:
            self.destroy()

    def destroy(self) -> None:
        if self._cofre:
            self._cofre.bloquear()
        if self._id_fila:
            self.after_cancel(self._id_fila)
            self._id_fila = None
        super().destroy()


def iniciar() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            # Faz o Windows mostrar o ícone do app na barra de tarefas (e não o do Python).
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("automacoes.pricebot")
        except (AttributeError, OSError):
            pass
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    AplicativoPriceBot().mainloop()
