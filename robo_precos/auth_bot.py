# -*- coding: utf-8 -*-
"""
auth_bot.py
-----------
Fluxo de autenticação no automationexercise.com:

    1. Abre /login e tenta entrar com e-mail + senha.
    2. Se o site responder "Your email or password is incorrect!", assume que
       a conta ainda não existe e faz o cadastro completo
       (Signup -> Account Information -> Continue).
    3. Confirma a sessão checando o texto "Logged in as" no cabeçalho.

Em vez de pausas fixas (wait_for_timeout), cada passo espera pela PRIMEIRA
resposta visível do site (sucesso OU erro) — mais rápido e mais confiável.
Os seletores data-qa="..." são os oficiais documentados pelo próprio site.
"""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from . import config
from .cofre import mascarar_email
from .relator import Relator


class FalhaAutenticacao(Exception):
    """Erro no fluxo de login/cadastro."""


def _texto(page: Page, trecho: str):
    return page.get_by_text(trecho, exact=False)


def _esta_logado(page: Page, timeout_ms: int = 5_000) -> bool:
    try:
        _texto(page, "Logged in as").first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def _tentar_login(page: Page, email: str, senha: str, relator: Relator) -> bool:
    relator.log(f"Tentando login com {mascarar_email(email)}")
    page.goto(config.LOGIN_URL, wait_until="domcontentloaded")

    page.locator('[data-qa="login-email"]').fill(email)
    page.locator('[data-qa="login-password"]').fill(senha)
    page.locator('[data-qa="login-button"]').click()

    logado = _texto(page, "Logged in as")
    erro = _texto(page, "Your email or password is incorrect!")
    try:
        logado.or_(erro).first.wait_for(state="visible", timeout=config.TIMEOUT_PADRAO_MS)
    except PlaywrightTimeoutError:
        relator.log("O site não confirmou o login nem mostrou erro.", "aviso")
        return False

    if logado.first.is_visible():
        relator.log("Login realizado com sucesso", "ok")
        return True

    relator.log("Conta não encontrada (ou senha diferente) — vou tentar cadastrar.", "aviso")
    return False


def _cadastrar_conta(page: Page, email: str, senha: str, dados: dict, relator: Relator) -> None:
    relator.log(f"Cadastrando nova conta para {mascarar_email(email)}")
    if "/login" not in page.url:
        page.goto(config.LOGIN_URL, wait_until="domcontentloaded")

    page.locator('[data-qa="signup-name"]').fill(dados.get("nome", "Usuario Teste"))
    page.locator('[data-qa="signup-email"]').fill(email)
    page.locator('[data-qa="signup-button"]').click()

    campo_senha = page.locator('[data-qa="password"]')
    email_existe = _texto(page, "Email Address already exist!")
    campo_senha.or_(email_existe).first.wait_for(state="visible", timeout=config.TIMEOUT_PADRAO_MS)

    if email_existe.first.is_visible():
        raise FalhaAutenticacao(
            f"O e-mail {mascarar_email(email)} já existe no site, mas a senha salva não confere. "
            "Escolha ou adicione outra conta no “Cofre de contas”."
        )

    # --- Página "Enter Account Information" ---
    if dados.get("titulo", "Mr").lower().startswith("mrs"):
        page.locator("#id_gender2").check()
    else:
        page.locator("#id_gender1").check()

    campo_senha.fill(senha)
    page.locator("#days").select_option(str(dados.get("dia_nascimento", "1")))
    page.locator("#months").select_option(str(dados.get("mes_nascimento", "1")))
    page.locator("#years").select_option(str(dados.get("ano_nascimento", "1990")))

    if dados.get("newsletter"):
        page.locator("#newsletter").check()
    if dados.get("ofertas_especiais"):
        page.locator("#optin").check()

    page.locator('[data-qa="first_name"]').fill(dados.get("nome", "Usuario"))
    page.locator('[data-qa="last_name"]').fill(dados.get("sobrenome", "Teste"))
    page.locator('[data-qa="address"]').fill(dados.get("endereco1", "Rua Teste 123"))
    if dados.get("endereco2"):
        page.locator('[data-qa="address2"]').fill(dados["endereco2"])

    # O select de países do site só aceita: India, United States, Canada,
    # Australia, Israel, New Zealand, Singapore.
    page.locator('[data-qa="country"]').select_option(dados.get("pais", "India"))
    page.locator('[data-qa="state"]').fill(dados.get("estado", "SP"))
    page.locator('[data-qa="city"]').fill(dados.get("cidade", "Sao Paulo"))
    page.locator('[data-qa="zipcode"]').fill(dados.get("cep", "01000-000"))
    page.locator('[data-qa="mobile_number"]').fill(dados.get("telefone", "11999999999"))
    page.locator('[data-qa="create-account-button"]').click()

    # --- Página "ACCOUNT CREATED!" ---
    page.locator('[data-qa="account-created"]').wait_for(state="visible", timeout=config.TIMEOUT_PADRAO_MS)
    relator.log("Conta criada no site", "ok")
    page.locator('[data-qa="continue-button"]').click()

    if not _esta_logado(page, config.TIMEOUT_PADRAO_MS):
        raise FalhaAutenticacao(
            "Cadastro concluído, mas o login automático não foi confirmado."
        )
    relator.log("Login automático confirmado", "ok")


def autenticar(page: Page, email: str, senha: str, dados_cadastro: dict, relator: Relator) -> str:
    """Tenta logar; se não der, cadastra. Retorna "login" ou "cadastro".
    Lança FalhaAutenticacao se nada funcionar."""
    if _tentar_login(page, email, senha, relator):
        return "login"
    relator.checar_cancelamento()
    _cadastrar_conta(page, email, senha, dados_cadastro, relator)
    return "cadastro"
