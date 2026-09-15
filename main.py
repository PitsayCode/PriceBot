# -*- coding: utf-8 -*-
"""
main.py
--------
Versão linha de comando do robô (a interface gráfica fica em app.py).

Uso:
    python main.py                       # login com a conta usada mais recentemente no cofre
    python main.py --conta EMAIL         # escolhe a conta do cofre pelo e-mail
    python main.py --mostrar-navegador   # acompanha o navegador na tela
    python main.py --sem-login           # coleta como visitante
    python main.py --demo                # simulação com dados fictícios

Contas: python gerenciar_contas.py adicionar
"""

from __future__ import annotations

import argparse
import getpass
import sys

from robo_precos import __version__, config, pipeline
from robo_precos.analise import formatar_preco, resumir
from robo_precos.cofre import Cofre, mascarar_email
from robo_precos.relator import Cancelado, Relator


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=f"{config.APP_NOME} — robô de preços (automationexercise.com)")
    parser.add_argument("--conta", metavar="EMAIL", help="e-mail da conta do cofre a usar no login")
    parser.add_argument("--sem-login", action="store_true", help="não autentica no site")
    parser.add_argument("--mostrar-navegador", action="store_true", help="abre o Chromium visível")
    parser.add_argument("--demo", action="store_true", help="simulação offline com dados fictícios")
    args = parser.parse_args()

    print(f"=== {config.APP_NOME} v{__version__} — {config.APP_SUBTITULO} ===\n")
    relator = Relator()
    cofre: Cofre | None = None

    try:
        if args.demo:
            resultado = pipeline.executar_demo(relator, ritmo=0.3)
        else:
            conta_id = None
            if not args.sem_login:
                if not Cofre.existe():
                    print("[ERRO] Nenhum cofre de contas criado. Rode: python gerenciar_contas.py adicionar "
                          "(ou use --sem-login).")
                    return 1
                cofre = Cofre.abrir(getpass.getpass("Senha-mestra do cofre: "))
                conta = cofre.buscar_por_email(args.conta) if args.conta else next(iter(cofre.listar()), None)
                if conta is None:
                    print("[ERRO] Conta não encontrada no cofre. Adicione com: python gerenciar_contas.py adicionar")
                    return 1
                print(f"Usando a conta {mascarar_email(conta.email)}\n")
                conta_id = conta.id

            opcoes = pipeline.OpcoesExecucao(
                autenticar=not args.sem_login,
                headless=not args.mostrar_navegador,
                cofre=cofre,
                conta_id=conta_id,
            )
            resultado = pipeline.executar(opcoes, relator)
    except (KeyboardInterrupt, Cancelado):
        print("\nInterrompido.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERRO] {(str(exc).strip().splitlines() or [type(exc).__name__])[0]}")
        return 1
    finally:
        if cofre:
            cofre.bloquear()

    resumo = resumir(resultado.produtos)
    print(f"\n[OK] {resumo.total} produtos em {resultado.duracao_s:.1f}s")
    print(f"     Menor {formatar_preco(resumo.minimo, resumo.moeda)} · "
          f"médio {formatar_preco(resumo.media, resumo.moeda)} · "
          f"maior {formatar_preco(resumo.maximo, resumo.moeda)}")
    print(f"     Excel: {resultado.caminho_excel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
