# -*- coding: utf-8 -*-
"""
pipeline.py
-----------
Orquestra o robô completo (usado pela interface e pela linha de comando):

    1. Descriptografa a conta escolhida no cofre (se o login estiver ativado).
    2. Abre o Chromium (Playwright) com bloqueio de anúncios.
    3. Autentica no site — login, ou cadastro automático se preciso — e
       registra o acesso (sucesso ou falha) no cofre criptografado.
    4. Coleta todos os produtos, com categoria e marca.
    5. Classifica em faixas e exporta o Excel com resumo e gráficos.
    6. Guarda a última coleta em JSON (a interface reabre com ela).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .classify_export import montar_planilha, nome_arquivo_excel
from .cofre import Cofre, Conta, mascarar_email
from .demo_data import produtos_demo
from .modelos import Produto
from .relator import Cancelado, Relator


@dataclass
class OpcoesExecucao:
    autenticar: bool = True
    headless: bool = config.HEADLESS
    cofre: Cofre | None = None                  # cofre já desbloqueado
    conta_id: str | None = None                 # conta do cofre usada no login
    pasta_saida: Path = field(default_factory=lambda: config.PASTA_SAIDA)


@dataclass
class ResultadoExecucao:
    produtos: list[Produto]
    caminho_excel: Path
    duracao_s: float
    gerado_em: datetime
    demonstracao: bool = False


def executar(opcoes: OpcoesExecucao, relator: Relator) -> ResultadoExecucao:
    # Importado aqui para o modo demonstração funcionar mesmo sem Playwright.
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    from .price_scraper import bloquear_anuncios, coletar_todos_os_precos

    inicio = time.perf_counter()
    relator.log(
        f"Iniciando coleta · login {'ativado' if opcoes.autenticar else 'desativado'} · "
        f"navegador {'invisível' if opcoes.headless else 'visível'}"
    )

    conta = None
    if opcoes.autenticar:
        if opcoes.cofre is None or opcoes.conta_id is None:
            raise RuntimeError("Login ativado, mas nenhuma conta do cofre foi escolhida.")
        relator.progresso(0.02, "Descriptografando a conta no cofre")
        conta = opcoes.cofre.obter(opcoes.conta_id)
        relator.log(f"Conta {mascarar_email(conta.email)} descriptografada do cofre", "ok")
    relator.checar_cancelamento()

    relator.progresso(0.06, "Abrindo o navegador")
    with sync_playwright() as pw:
        try:
            navegador = pw.chromium.launch(
                headless=opcoes.headless, slow_mo=0 if opcoes.headless else 120
            )
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                raise RuntimeError(
                    "O navegador do Playwright não está instalado. Rode o Iniciar.bat "
                    "novamente (ou: python -m playwright install chromium)."
                ) from exc
            raise

        try:
            contexto = navegador.new_context(viewport={"width": 1366, "height": 860}, locale="en-US")
            bloquear_anuncios(contexto, bloquear_imagens=opcoes.headless)
            pagina = contexto.new_page()
            pagina.set_default_timeout(config.TIMEOUT_PADRAO_MS)
            relator.log("Chromium iniciado (anúncios bloqueados)", "ok")

            if conta is not None:
                relator.progresso(0.12, "Autenticando no site")
                _autenticar_e_registrar(pagina, opcoes.cofre, conta, relator)
            else:
                relator.log("Coletando como visitante (sem login)")
            relator.checar_cancelamento()

            produtos = coletar_todos_os_precos(pagina, relator, inicio=0.25, fim=0.88)
        finally:
            navegador.close()

    if not produtos:
        raise RuntimeError("Nenhum produto foi coletado. O layout do site pode ter mudado.")

    return _finalizar(produtos, opcoes.pasta_saida, relator, inicio, config.PREFIXO_ARQUIVO_EXCEL)


def _autenticar_e_registrar(pagina, cofre: Cofre, conta: Conta, relator: Relator) -> None:
    """Faz login/cadastro e grava o resultado — sucesso ou falha — no histórico cifrado da conta."""
    from .auth_bot import autenticar

    try:
        modo = autenticar(pagina, conta.email, conta.senha, config.DADOS_CADASTRO, relator)
    except Cancelado:
        raise
    except Exception as exc:
        motivo = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        cofre.registrar_login(conta.id, "falha", motivo)
        relator.log("Falha de acesso registrada no cofre (criptografada)", "aviso")
        raise
    atualizada = cofre.registrar_login(conta.id, modo)
    relator.log(f"Acesso nº {atualizada.total_logins} registrado no cofre (criptografado)", "ok")


def executar_demo(relator: Relator, pasta_saida: Path | None = None, ritmo: float = 1.0) -> ResultadoExecucao:
    """Simula a execução completa com dados fictícios (ótimo para gravar vídeo)."""
    inicio = time.perf_counter()

    def pausa(segundos: float) -> None:
        fim = time.perf_counter() + segundos * ritmo
        while time.perf_counter() < fim:
            relator.checar_cancelamento()
            time.sleep(0.04)
        relator.checar_cancelamento()

    produtos = produtos_demo()
    relator.log("Modo demonstração: dados fictícios, sem acessar o site.", "aviso")

    relator.progresso(0.05, "Abrindo o navegador")
    pausa(0.7)
    relator.log("Chromium iniciado (anúncios bloqueados)", "ok")

    relator.progresso(0.12, "Autenticando no site")
    email_demo = mascarar_email("pricebot.demo@example.com")
    relator.log(f"Conta {email_demo} descriptografada do cofre", "ok")
    relator.log(f"Tentando login com {email_demo}")
    pausa(1.0)
    relator.log("Login realizado com sucesso", "ok")
    relator.log("Acesso registrado no cofre (criptografado)", "ok")

    relator.progresso(0.25, "Lendo a vitrine de produtos")
    pausa(0.9)
    relator.log(f"{len(produtos)} produtos encontrados em /products", "ok")

    categorias = sorted({(p.categoria_grupo, p.categoria_sub) for p in produtos})
    marcas = sorted({p.marca for p in produtos})
    relator.log(f"Menu lateral: {len(categorias)} subcategorias e {len(marcas)} marcas")

    paginas = [
        ("Categoria", f"{g} / {s}", sum(p.categoria_grupo == g and p.categoria_sub == s for p in produtos))
        for g, s in categorias
    ] + [("Marca", m, sum(p.marca == m for p in produtos)) for m in marcas]

    for i, (tipo, rotulo, quantidade) in enumerate(paginas, start=1):
        relator.progresso(0.25 + 0.63 * i / len(paginas), f"Mapeando {tipo.lower()}: {rotulo}")
        pausa(0.4)
        relator.log(f"→ {tipo} {rotulo}: {quantidade} produtos")

    relator.log(
        f"Categoria identificada para {len(produtos)}/{len(produtos)} e marca para "
        f"{len(produtos)}/{len(produtos)} produtos",
        "ok",
    )
    return _finalizar(
        produtos, pasta_saida or config.PASTA_SAIDA, relator, inicio,
        f"EXEMPLO_{config.PREFIXO_ARQUIVO_EXCEL}", demonstracao=True,
    )


def _finalizar(
    produtos: list[Produto], pasta_saida: Path, relator: Relator, inicio: float,
    prefixo: str, demonstracao: bool = False,
) -> ResultadoExecucao:
    relator.evento("produtos", produtos=produtos)
    relator.progresso(0.93, "Classificando preços e gerando o Excel")

    agora = datetime.now()
    caminho = montar_planilha(produtos, pasta_saida / nome_arquivo_excel(prefixo, agora), agora)
    relator.log(f"Excel salvo: {caminho.name}", "ok")

    resultado = ResultadoExecucao(
        produtos=produtos,
        caminho_excel=caminho,
        duracao_s=time.perf_counter() - inicio,
        gerado_em=agora,
        demonstracao=demonstracao,
    )
    try:
        salvar_ultima_coleta(resultado)
    except OSError as exc:
        relator.log(f"Não consegui salvar o histórico da coleta: {exc}", "aviso")

    relator.progresso(1.0, "Concluído")
    return resultado


def salvar_ultima_coleta(resultado: ResultadoExecucao) -> None:
    config.ARQUIVO_ULTIMA_COLETA.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "gerado_em": resultado.gerado_em.isoformat(timespec="seconds"),
        "duracao_s": round(resultado.duracao_s, 2),
        "demonstracao": resultado.demonstracao,
        "caminho_excel": str(resultado.caminho_excel),
        "produtos": [p.para_dict() for p in resultado.produtos],
    }
    config.ARQUIVO_ULTIMA_COLETA.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def carregar_ultima_coleta() -> ResultadoExecucao | None:
    try:
        payload = json.loads(config.ARQUIVO_ULTIMA_COLETA.read_text(encoding="utf-8"))
        return ResultadoExecucao(
            produtos=[Produto.de_dict(d) for d in payload["produtos"]],
            caminho_excel=Path(payload["caminho_excel"]),
            duracao_s=float(payload.get("duracao_s", 0)),
            gerado_em=datetime.fromisoformat(payload["gerado_em"]),
            demonstracao=bool(payload.get("demonstracao", False)),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
