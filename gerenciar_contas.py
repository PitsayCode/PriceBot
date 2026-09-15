# -*- coding: utf-8 -*-
"""
gerenciar_contas.py
--------------------
Gerencia o cofre criptografado de contas pelo terminal
(na interface gráfica: botão “Cofre de contas”).

Uso:
    python gerenciar_contas.py adicionar       # cria o cofre (se preciso) e adiciona/atualiza uma conta
    python gerenciar_contas.py listar          # contas, status e nº de logins
    python gerenciar_contas.py remover EMAIL
    python gerenciar_contas.py trocar-senha    # troca a senha-mestra
    python gerenciar_contas.py invasor         # o que alguém vê abrindo o banco SEM a senha
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys

from robo_precos.cofre import Cofre, mascarar_email, relatorio_invasor


def _nova_senha_mestra(rotulo: str) -> str | None:
    senha = getpass.getpass(rotulo)
    if senha != getpass.getpass("Confirme a senha-mestra: "):
        print("[ERRO] As senhas-mestras não coincidem.")
        return None
    return senha


def _abrir(permitir_criar: bool) -> Cofre | None:
    if Cofre.existe():
        return Cofre.abrir(getpass.getpass("Senha-mestra do cofre: "))
    if not permitir_criar:
        print("[ERRO] Nenhum cofre criado. Rode: python gerenciar_contas.py adicionar")
        return None
    print("Nenhum cofre encontrado — vamos criar um.")
    senha = _nova_senha_mestra("Crie uma senha-mestra (mínimo 8 caracteres): ")
    return Cofre.criar(senha) if senha else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Cofre criptografado de contas do PriceBot")
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("adicionar", help="adiciona (ou atualiza) uma conta; cria o cofre se preciso")
    comandos.add_parser("listar", help="lista as contas do cofre")
    comandos.add_parser("remover", help="remove uma conta").add_argument("email")
    comandos.add_parser("trocar-senha", help="troca a senha-mestra")
    comandos.add_parser("invasor", help="mostra o que alguém vê abrindo o banco sem a senha")
    args = parser.parse_args()

    if args.comando == "invasor":
        print(relatorio_invasor())
        return 0

    cofre: Cofre | None = None
    try:
        cofre = _abrir(permitir_criar=args.comando == "adicionar")
        if cofre is None:
            return 1

        if args.comando == "adicionar":
            email = input("E-mail da conta: ").strip()
            senha = getpass.getpass("Senha da conta: ")
            if senha != getpass.getpass("Confirme a senha da conta: "):
                print("[ERRO] As senhas não coincidem.")
                return 1
            conta = cofre.salvar_conta(email, senha, input("Apelido (opcional): "))
            print(f"[OK] Conta {mascarar_email(conta.email)} salva no cofre (criptografada).")

        elif args.comando == "listar":
            contas = cofre.listar()
            if not contas:
                print("Cofre vazio.")
            for c in contas:
                print(f"- {c.email:<42} {c.status:<7} {c.total_logins:>3} login(s) · "
                      f"último: {c.ultimo_login or 'nunca'}")

        elif args.comando == "remover":
            conta = cofre.buscar_por_email(args.email)
            if conta is None:
                print("[ERRO] Esse e-mail não está no cofre.")
                return 1
            cofre.remover(conta.id)
            print(f"[OK] Conta {mascarar_email(conta.email)} removida.")

        elif args.comando == "trocar-senha":
            atual = getpass.getpass("Senha-mestra atual: ")
            nova = _nova_senha_mestra("Nova senha-mestra (mínimo 8 caracteres): ")
            if not nova:
                return 1
            cofre.trocar_senha_mestra(atual, nova)
            print("[OK] Senha-mestra alterada.")

    except (ValueError, KeyError, OSError, sqlite3.DatabaseError) as exc:
        print(f"[ERRO] {exc}")
        return 1
    finally:
        if cofre:
            cofre.bloquear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
