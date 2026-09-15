# -*- coding: utf-8 -*-
"""
dialogos.py
-----------
Janelas modais do cofre de contas: criar, desbloquear, gerenciar contas,
adicionar conta, trocar a senha-mestra e a "visão do invasor".
"""

from __future__ import annotations

import sqlite3
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from ..cofre import (
    MIN_SENHA_MESTRA, Cofre, Conta, SenhaMestraIncorreta, gerar_conta_de_teste, relatorio_invasor,
)
from . import tema
from .icone import garantir_icone

MASCARA = "•"


def _escala(widget: tk.Misc) -> float:
    return ctk.ScalingTracker.get_widget_scaling(widget)


def _data(iso: str | None) -> str:
    if not iso:
        return "nunca"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


class _Dialogo(ctk.CTkToplevel):
    LARGURA = 400

    def __init__(self, master, titulo: str):
        super().__init__(master, fg_color=tema.FUNDO)
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        self.resultado = None
        self._foco_inicial: tk.Widget | None = None
        self._linha = 0
        self._entradas_mascaradas: tuple[ctk.CTkEntry, ...] = ()

        self.protocol("WM_DELETE_WINDOW", self._cancelar)
        self.bind("<Escape>", lambda _e: self._cancelar())
        self.bind("<Return>", lambda _e: self._confirmar())

        icone = garantir_icone()
        if icone and sys.platform == "win32":
            self.after(250, lambda: self.iconbitmap(str(icone)))

        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.pack(fill="both", expand=True, padx=32, pady=28)
        self.corpo.grid_columnconfigure(0, weight=1)

    # --- blocos de layout ---------------------------------------------------
    def _proxima(self) -> int:
        self._linha += 1
        return self._linha

    def _texto(self, texto: str, cor: str, tamanho: int = 13, peso: str = "normal", pady=(0, 0)) -> ctk.CTkLabel:
        rotulo = ctk.CTkLabel(self.corpo, text=texto, font=tema.fonte(tamanho, peso), text_color=cor, anchor="w",
                              justify="left", wraplength=round(self.LARGURA * _escala(self)))
        rotulo.grid(row=self._proxima(), column=0, sticky="ew", pady=pady)
        return rotulo

    def _titulo(self, texto: str, descricao: str) -> None:
        self._texto(texto, tema.TEXTO, 20, "bold")
        self._texto(descricao, tema.TEXTO_SUAVE, pady=(4, 18))

    def _campo(self, rotulo: str, senha: bool = False) -> ctk.CTkEntry:
        ctk.CTkLabel(self.corpo, text=rotulo, font=tema.fonte(12, "bold"), text_color=tema.TEXTO_SUAVE,
                     anchor="w").grid(row=self._proxima(), column=0, sticky="ew")
        entrada = ctk.CTkEntry(self.corpo, width=self.LARGURA, height=40, corner_radius=10, font=tema.fonte(14),
                               fg_color=tema.CARTAO, border_color=tema.BORDA, text_color=tema.TEXTO)
        if senha:
            entrada.configure(show=MASCARA)
        entrada.grid(row=self._proxima(), column=0, sticky="ew", pady=(4, 12))
        return entrada

    def _checkbox_mostrar(self, entradas: tuple[ctk.CTkEntry, ...]) -> ctk.CTkCheckBox:
        self._entradas_mascaradas = entradas
        self._ck_mostrar = ctk.CTkCheckBox(self.corpo, text="Mostrar senhas", font=tema.fonte(12),
                                           text_color=tema.TEXTO_SUAVE, fg_color=tema.PRIMARIA,
                                           hover_color=tema.PRIMARIA_HOVER, border_color=tema.BORDA,
                                           command=self._alternar_mascara)
        self._ck_mostrar.grid(row=self._proxima(), column=0, sticky="w", pady=(0, 8))
        return self._ck_mostrar

    def _alternar_mascara(self) -> None:
        mascara = "" if self._ck_mostrar.get() else MASCARA
        for entrada in self._entradas_mascaradas:
            entrada.configure(show=mascara)

    def _mensagem_erro(self) -> None:
        self.lb_erro = self._texto("", tema.ERRO, 12)

    def _erro(self, texto: str) -> None:
        self.lb_erro.configure(text=texto, text_color=tema.ERRO)

    def _ocupado(self, texto: str) -> None:
        self.lb_erro.configure(text=texto, text_color=tema.TEXTO_SUAVE)
        self.update_idletasks()

    def _botao(self, master, texto: str, comando, primario: bool = False, largura: int = 120) -> ctk.CTkButton:
        if primario:
            return ctk.CTkButton(master, text=texto, width=largura, height=40, corner_radius=10,
                                 font=tema.fonte(13, "bold"), fg_color=tema.PRIMARIA,
                                 hover_color=tema.PRIMARIA_HOVER, command=comando)
        return ctk.CTkButton(master, text=texto, width=largura, height=40, corner_radius=10, font=tema.fonte(13),
                             fg_color="transparent", border_width=1, border_color=tema.BORDA,
                             hover_color=tema.CARTAO_HOVER, text_color=tema.TEXTO, command=comando)

    def _botoes(self, texto_confirmar: str) -> None:
        linha = ctk.CTkFrame(self.corpo, fg_color="transparent")
        linha.grid(row=self._proxima(), column=0, sticky="e", pady=(12, 0))
        self._botao(linha, "Cancelar", self._cancelar, largura=110).pack(side="left", padx=(0, 10))
        self._botao(linha, texto_confirmar, self._confirmar, primario=True, largura=160).pack(side="left")

    # --- ciclo de vida ------------------------------------------------------
    def mostrar(self):
        self.update_idletasks()
        mestre = self.master
        x = mestre.winfo_rootx() + (mestre.winfo_width() - self.winfo_reqwidth()) // 2
        y = mestre.winfo_rooty() + (mestre.winfo_height() - self.winfo_reqheight()) // 3
        self.wm_geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(60, self._capturar_foco)
        self.wait_window()
        return self.resultado

    def _capturar_foco(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            self.after(60, self._capturar_foco)
            return
        self.lift()
        self.focus_force()
        if self._foco_inicial is not None:
            self._foco_inicial.focus_set()

    def _cancelar(self) -> None:
        self.resultado = None
        self.destroy()

    def _confirmar(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Criar / desbloquear
# ---------------------------------------------------------------------------
class DialogoCriarCofre(_Dialogo):
    """Cria dados/cofre.db. Retorna o Cofre já desbloqueado."""

    def __init__(self, master):
        super().__init__(master, "Criar cofre de contas")
        self._titulo(
            "Crie o seu cofre de contas",
            "Toda conta usada pelo robô fica num banco SQLite totalmente criptografado "
            "(AES-256-GCM + scrypt). Quem abrir o arquivo vê só bytes embaralhados — nem os e-mails aparecem.",
        )
        self.e_senha = self._campo(f"Senha-mestra (mínimo {MIN_SENHA_MESTRA} caracteres)", senha=True)
        self.e_confirma = self._campo("Confirme a senha-mestra", senha=True)
        self._checkbox_mostrar((self.e_senha, self.e_confirma))
        self._texto("⚠  Não existe recuperação: sem a senha-mestra ninguém — nem você — consegue ler as contas.",
                    tema.AVISO, 12, pady=(4, 4))
        self._mensagem_erro()
        self._botoes("Criar cofre")
        self._foco_inicial = self.e_senha

    def _confirmar(self) -> None:
        senha, confirma = self.e_senha.get(), self.e_confirma.get()
        if len(senha) < MIN_SENHA_MESTRA:
            return self._erro(f"A senha-mestra precisa ter pelo menos {MIN_SENHA_MESTRA} caracteres.")
        if senha != confirma:
            return self._erro("As senhas-mestras não coincidem.")
        self._ocupado("Derivando a chave com scrypt…")
        try:
            self.resultado = Cofre.criar(senha)
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            return self._erro(str(exc))
        self.destroy()


class DialogoDesbloquear(_Dialogo):
    """Pede a senha-mestra. Retorna o Cofre desbloqueado ou None."""

    def __init__(self, master):
        super().__init__(master, "Desbloquear cofre")
        n = Cofre.quantidade()
        self._titulo(
            "Desbloquear o cofre",
            f"{n} conta{'s' if n != 1 else ''} protegida{'s' if n != 1 else ''} com AES-256-GCM.\n"
            "Digite a senha-mestra — ela nunca é gravada em disco.",
        )
        self.e_senha = self._campo("Senha-mestra", senha=True)
        self._mensagem_erro()
        self._botoes("Desbloquear")
        self._foco_inicial = self.e_senha

    def _confirmar(self) -> None:
        senha = self.e_senha.get()
        if not senha:
            return self._erro("Digite a senha-mestra.")
        self._ocupado("Verificando…")
        try:
            self.resultado = Cofre.abrir(senha)
        except SenhaMestraIncorreta as exc:
            self.e_senha.delete(0, "end")
            return self._erro(str(exc))
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            return self._erro(f"Não foi possível abrir o cofre: {exc}")
        self.destroy()


# ---------------------------------------------------------------------------
# Contas
# ---------------------------------------------------------------------------
class DialogoNovaConta(_Dialogo):
    """Adiciona (ou atualiza) uma conta no cofre. Retorna a Conta salva."""

    def __init__(self, master, cofre: Cofre):
        super().__init__(master, "Nova conta")
        self._cofre = cofre
        self._titulo(
            "Adicionar conta ao cofre",
            "Se a conta ainda não existir no site, o robô faz o cadastro no primeiro uso. "
            "Se o e-mail já estiver no cofre, só a senha é atualizada.",
        )
        self.e_apelido = self._campo("Apelido (opcional)")
        self.e_email = self._campo("E-mail")
        self.e_senha = self._campo("Senha da conta", senha=True)
        ctk.CTkButton(self.corpo, text="✦  Gerar conta de teste automaticamente", height=34, corner_radius=10,
                      font=tema.fonte(12, "bold"), fg_color=tema.CARTAO, hover_color=tema.CARTAO_HOVER,
                      text_color=tema.SECUNDARIA, command=self._gerar
                      ).grid(row=self._proxima(), column=0, sticky="w", pady=(0, 12))
        self._checkbox_mostrar((self.e_senha,))
        self._mensagem_erro()
        self._botoes("Salvar no cofre")
        self._foco_inicial = self.e_email

    def _gerar(self) -> None:
        email, senha = gerar_conta_de_teste()
        for entrada, valor in ((self.e_email, email), (self.e_senha, senha)):
            entrada.delete(0, "end")
            entrada.insert(0, valor)
        if not self.e_apelido.get():
            self.e_apelido.insert(0, f"Teste {datetime.now():%d/%m %H:%M}")
        self._ck_mostrar.select()
        self._alternar_mascara()

    def _confirmar(self) -> None:
        self._ocupado("Criptografando…")
        try:
            self.resultado = self._cofre.salvar_conta(self.e_email.get(), self.e_senha.get(), self.e_apelido.get())
        except (ValueError, sqlite3.DatabaseError) as exc:
            return self._erro(str(exc))
        self.destroy()


class DialogoTrocarSenha(_Dialogo):
    """Re-embrulha a chave dos dados com uma nova senha-mestra. Retorna True."""

    def __init__(self, master, cofre: Cofre):
        super().__init__(master, "Trocar senha-mestra")
        self._cofre = cofre
        self._titulo(
            "Trocar a senha-mestra",
            "Só a chave que protege os dados é recriptografada — as contas continuam intactas.",
        )
        self.e_atual = self._campo("Senha-mestra atual", senha=True)
        self.e_nova = self._campo(f"Nova senha-mestra (mínimo {MIN_SENHA_MESTRA} caracteres)", senha=True)
        self.e_confirma = self._campo("Confirme a nova senha-mestra", senha=True)
        self._checkbox_mostrar((self.e_atual, self.e_nova, self.e_confirma))
        self._mensagem_erro()
        self._botoes("Trocar senha")
        self._foco_inicial = self.e_atual

    def _confirmar(self) -> None:
        if self.e_nova.get() != self.e_confirma.get():
            return self._erro("As novas senhas não coincidem.")
        self._ocupado("Derivando as chaves com scrypt…")
        try:
            self._cofre.trocar_senha_mestra(self.e_atual.get(), self.e_nova.get())
        except (ValueError, sqlite3.DatabaseError) as exc:
            return self._erro(str(exc))
        self.resultado = True
        self.destroy()


class DialogoCofre(_Dialogo):
    """Gerenciador do cofre. Retorna o id da conta escolhida (ou None)."""

    LARGURA = 660
    STATUS = {
        "ativa": ("ativa", tema.SUCESSO),
        "falhou": ("falhou", tema.ERRO),
        "nova": ("nunca usada", tema.TEXTO_SUAVE),
    }

    def __init__(self, master, cofre: Cofre, conta_atual: str | None = None):
        super().__init__(master, "Cofre de contas")
        self._cofre = cofre
        self._selecao = tk.StringVar(value=conta_atual or "")

        self._titulo(
            "Cofre de contas",
            "Cada login feito pelo robô fica registrado aqui. Cada conta é um registro AES-256-GCM "
            "independente e o e-mail é substituído por um índice cego (HMAC) no banco.",
        )

        self._abas = ctk.CTkSegmentedButton(
            self.corpo, values=["Contas", "Visão do invasor"], command=self._trocar_aba, height=34,
            font=tema.fonte(12, "bold"), fg_color=tema.CARTAO, selected_color=tema.PRIMARIA,
            selected_hover_color=tema.PRIMARIA_HOVER, unselected_color=tema.CARTAO,
            unselected_hover_color=tema.CARTAO_HOVER, text_color=tema.TEXTO)
        self._abas.set("Contas")
        self._abas.grid(row=self._proxima(), column=0, sticky="w", pady=(0, 12))

        linha = self._proxima()
        self.corpo.grid_rowconfigure(linha, weight=1)
        self.lista = ctk.CTkScrollableFrame(self.corpo, width=self.LARGURA, height=320, fg_color=tema.CARTAO,
                                            corner_radius=12, scrollbar_button_color=tema.BORDA,
                                            scrollbar_button_hover_color=tema.TEXTO_FRACO)
        self.lista.grid(row=linha, column=0, sticky="nsew")
        self.lista.grid_columnconfigure(0, weight=1)
        self.invasor = ctk.CTkTextbox(self.corpo, width=self.LARGURA, height=320, corner_radius=12, wrap="none",
                                      fg_color="#05070D", text_color="#7CFFB2", border_width=1,
                                      border_color=tema.BORDA, font=ctk.CTkFont(family=tema.FAMILIA_MONO, size=12))
        self.invasor.grid(row=linha, column=0, sticky="nsew")
        self.invasor.grid_remove()

        self._mensagem_erro()

        acoes = ctk.CTkFrame(self.corpo, fg_color="transparent")
        acoes.grid(row=self._proxima(), column=0, sticky="ew", pady=(10, 0))
        acoes.grid_columnconfigure(2, weight=1)
        self._botao(acoes, "+  Nova conta", self._nova_conta, largura=130).grid(row=0, column=0, padx=(0, 8))
        self._botao(acoes, "Trocar senha-mestra", self._trocar_senha, largura=160).grid(row=0, column=1)
        self._botao(acoes, "Fechar", self._cancelar, largura=100).grid(row=0, column=3, padx=(0, 8))
        self._botao(acoes, "Usar esta conta", self._confirmar, primario=True, largura=150).grid(row=0, column=4)

        self._recarregar()

    # --- lista ----------------------------------------------------------------
    def _recarregar(self) -> None:
        for filho in self.lista.winfo_children():
            filho.destroy()
        try:
            contas = self._cofre.listar()
        except (ValueError, sqlite3.DatabaseError) as exc:
            return self._erro(str(exc))

        if not contas:
            self._selecao.set("")
            ctk.CTkLabel(self.lista, text="Nenhuma conta no cofre ainda.\nClique em “+  Nova conta” para adicionar a primeira.",
                         font=tema.fonte(13), text_color=tema.TEXTO_FRACO, justify="center"
                         ).grid(row=0, column=0, pady=110)
        else:
            if self._selecao.get() not in {c.id for c in contas}:
                self._selecao.set(contas[0].id)
            for i, conta in enumerate(contas):
                self._cartao_conta(i, conta)
        self._atualizar_invasor()

    def _cartao_conta(self, i: int, conta: Conta) -> None:
        cartao = ctk.CTkFrame(self.lista, fg_color=tema.FUNDO, corner_radius=10, border_width=1,
                              border_color=tema.BORDA)
        cartao.grid(row=i, column=0, sticky="ew", padx=6, pady=4)
        cartao.grid_columnconfigure(1, weight=1)

        selecionar = lambda _e=None, c=conta: self._selecao.set(c.id)  # noqa: E731
        ctk.CTkRadioButton(cartao, text="", variable=self._selecao, value=conta.id, width=24,
                           fg_color=tema.PRIMARIA, hover_color=tema.PRIMARIA_HOVER, border_color=tema.BORDA
                           ).grid(row=0, column=0, rowspan=2, padx=(14, 4), pady=12)

        titulo = ctk.CTkLabel(cartao, text=conta.apelido or conta.email, font=tema.fonte(14, "bold"),
                              text_color=tema.TEXTO, anchor="w")
        titulo.grid(row=0, column=1, sticky="ew", pady=(10, 0))
        logins = f"{conta.total_logins} login{'s' if conta.total_logins != 1 else ''}"
        prefixo = f"{conta.email}  ·  " if conta.apelido else ""
        detalhe = ctk.CTkLabel(cartao, text=f"{prefixo}{logins}  ·  último acesso: {_data(conta.ultimo_login)}",
                               font=tema.fonte(12), text_color=tema.TEXTO_FRACO, anchor="w")
        detalhe.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        texto, cor = self.STATUS.get(conta.status, (conta.status, tema.TEXTO_SUAVE))
        ctk.CTkLabel(cartao, text=f"  {texto}  ", height=24, corner_radius=8, font=tema.fonte(11, "bold"),
                     text_color=cor, fg_color=tema.misturar(cor, tema.FUNDO, 0.85)
                     ).grid(row=0, column=2, rowspan=2, padx=8)
        ctk.CTkButton(cartao, text="Remover", width=80, height=28, corner_radius=8, font=tema.fonte(12),
                      fg_color="transparent", border_width=1, border_color=tema.misturar(tema.ERRO, tema.FUNDO, 0.6),
                      hover_color=tema.misturar(tema.ERRO, tema.FUNDO, 0.85), text_color=tema.ERRO,
                      command=lambda c=conta: self._remover(c)).grid(row=0, column=3, rowspan=2, padx=(0, 12))

        for widget in (cartao, titulo, detalhe):
            widget.bind("<Button-1>", selecionar)

    def _atualizar_invasor(self) -> None:
        self.invasor.configure(state="normal")
        self.invasor.delete("1.0", "end")
        self.invasor.insert("1.0", relatorio_invasor(self._cofre.caminho))
        self.invasor.configure(state="disabled")

    def _trocar_aba(self, valor: str) -> None:
        if valor == "Contas":
            self.invasor.grid_remove()
            self.lista.grid()
        else:
            self._atualizar_invasor()
            self.lista.grid_remove()
            self.invasor.grid()

    # --- ações ------------------------------------------------------------------
    def _depois_de_subjanela(self) -> None:
        self.after(80, self._capturar_foco)

    def _nova_conta(self) -> None:
        conta = DialogoNovaConta(self, self._cofre).mostrar()
        if conta:
            self._selecao.set(conta.id)
            self._recarregar()
        self._depois_de_subjanela()

    def _trocar_senha(self) -> None:
        if DialogoTrocarSenha(self, self._cofre).mostrar():
            messagebox.showinfo("Cofre de contas", "Senha-mestra alterada com sucesso.", parent=self)
        self._depois_de_subjanela()

    def _remover(self, conta: Conta) -> None:
        if messagebox.askyesno(
            "Remover conta",
            f"Remover {conta.email} do cofre?\nO registro criptografado é sobrescrito no arquivo (secure_delete).",
            parent=self,
        ):
            self._cofre.remover(conta.id)
            self._recarregar()
        self._depois_de_subjanela()

    def _confirmar(self) -> None:
        if not self._selecao.get():
            return self._erro("Adicione uma conta para continuar.")
        self.resultado = self._selecao.get()
        self.destroy()
