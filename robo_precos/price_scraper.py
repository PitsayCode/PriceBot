# -*- coding: utf-8 -*-
"""
price_scraper.py
-----------------
Coleta TODOS os produtos e preços listados em /products e usa o menu
lateral (categorias Women / Men / Kids e marcas Polo, H&M, Biba...) para
descobrir a categoria e a marca de cada produto.

Otimizações em relação à versão 1:
    - Os cards são lidos com UMA chamada JavaScript por página
      (evaluate_all), em vez de ~4 chamadas Playwright por produto.
    - Anúncios e rastreadores são bloqueados na rede: páginas carregam
      bem mais rápido e não aparecem pop-ups por cima do site.

IMPORTANTE: o automationexercise.com é um site de TREINAMENTO de automação
de testes. Os preços são fictícios e aparecem em "Rs." (rúpias), a moeda
padrão do site — não é BRL.
"""

from __future__ import annotations

import re
from typing import Callable

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page, Route
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from . import config
from .modelos import Produto
from .relator import Relator

_PRECO_REGEX = re.compile(r"([^\d\s]+)\s*([\d.,]+)")

_JS_LER_CARDS = r"""
(cards) => cards.map((card) => {
  const info = card.querySelector('.productinfo');
  const texto = (seletor) => (info?.querySelector(seletor)?.textContent || '').trim();
  const link = card.querySelector('a[href*="/product_details/"]')?.getAttribute('href') || '';
  let id = card.querySelector('a.add-to-cart')?.getAttribute('data-product-id') || '';
  if (!id) {
    const m = link.match(/product_details\/(\d+)/);
    id = m ? m[1] : '';
  }
  return { id, nome: texto('p'), preco: texto('h2'), link };
})
"""

_JS_LER_MENU = r"""
() => ({
  categorias: [...document.querySelectorAll('#accordian .panel')].flatMap((painel) => {
    const grupo = (painel.querySelector('.panel-heading .panel-title')?.textContent || '').trim();
    return [...painel.querySelectorAll('a[href*="/category_products/"]')].map((a) => ({
      grupo, nome: a.textContent.trim(), href: a.getAttribute('href'),
    }));
  }),
  marcas: [...document.querySelectorAll('.brands-name a[href*="/brand_products/"]')].map((a) => ({
    nome: a.textContent.replace(/\(\d+\)/, '').trim(), href: a.getAttribute('href'),
  })),
})
"""


def _parse_preco(texto: str) -> tuple[str, float]:
    """'Rs. 1,500' -> ('Rs.', 1500.0)"""
    m = _PRECO_REGEX.search(texto.strip())
    if not m:
        return "Rs.", 0.0
    try:
        return m.group(1), float(m.group(2).replace(",", ""))
    except ValueError:
        return m.group(1), 0.0


def _limpar(texto: str) -> str:
    return " ".join(texto.split())


def _url_absoluta(href: str) -> str:
    return href if href.startswith("http") else f"{config.BASE_URL}{href}"


def bloquear_anuncios(contexto: BrowserContext, bloquear_imagens: bool = False) -> None:
    """Aborta requisições de anúncios/rastreadores (e, opcionalmente, imagens)."""

    def _rota(route: Route) -> None:
        requisicao = route.request
        if any(dominio in requisicao.url for dominio in config.DOMINIOS_BLOQUEADOS):
            route.abort()
        elif bloquear_imagens and requisicao.resource_type in ("image", "media", "font"):
            route.abort()
        else:
            route.continue_()

    contexto.route("**/*", _rota)


def _abrir(page: Page, url: str) -> None:
    for tentativa in (1, 2):
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.locator(".features_items").wait_for(state="attached")
            return
        except PlaywrightTimeoutError:
            if tentativa == 2:
                raise


def _ler_cards(page: Page) -> list[dict]:
    return page.locator(".features_items .product-image-wrapper").evaluate_all(_JS_LER_CARDS)


def coletar_todos_os_precos(
    page: Page, relator: Relator, inicio: float = 0.25, fim: float = 0.88
) -> list[Produto]:
    """Lista mestre em /products + enriquecimento por categoria e marca."""
    relator.progresso(inicio, "Lendo a vitrine de produtos")
    _abrir(page, config.PRODUCTS_URL)

    produtos: dict[str, Produto] = {}
    for i, card in enumerate(_ler_cards(page)):
        moeda, valor = _parse_preco(card["preco"])
        pid = card["id"] or f"sem-id-{i}"
        produtos.setdefault(
            pid,
            Produto(
                id_produto=pid,
                nome=_limpar(card["nome"]),
                preco_valor=valor,
                moeda=moeda,
                preco_texto=card["preco"],
                url=_url_absoluta(card["link"]) if card["link"] else "",
            ),
        )
    relator.log(f"{len(produtos)} produtos encontrados em /products", "ok")

    menu = page.evaluate(_JS_LER_MENU)
    relator.log(
        f"Menu lateral: {len(menu['categorias'])} subcategorias e {len(menu['marcas'])} marcas"
    )

    def _definir_categoria(grupo: str, sub: str) -> Callable[[Produto], None]:
        def aplicar(p: Produto) -> None:
            p.categoria_grupo, p.categoria_sub = grupo, sub
        return aplicar

    def _definir_marca(marca: str) -> Callable[[Produto], None]:
        def aplicar(p: Produto) -> None:
            p.marca = marca
        return aplicar

    paginas: list[tuple[str, str, str, Callable[[Produto], None]]] = []
    for c in menu["categorias"]:
        grupo, sub = _limpar(c["grupo"]).title(), _limpar(c["nome"])
        paginas.append(("Categoria", f"{grupo} / {sub}", c["href"], _definir_categoria(grupo, sub)))
    for m in menu["marcas"]:
        marca = _limpar(m["nome"])
        paginas.append(("Marca", marca, m["href"], _definir_marca(marca)))

    for i, (tipo, rotulo, href, aplicar) in enumerate(paginas, start=1):
        relator.checar_cancelamento()
        relator.progresso(inicio + (fim - inicio) * i / len(paginas), f"Mapeando {tipo.lower()}: {rotulo}")
        try:
            _abrir(page, _url_absoluta(href))
            cards = _ler_cards(page)
        except PlaywrightError as exc:
            relator.log(f"Não consegui ler {rotulo}: {str(exc).splitlines()[0]}", "aviso")
            continue
        for card in cards:
            if card["id"] in produtos:
                aplicar(produtos[card["id"]])
        relator.log(f"→ {tipo} {rotulo}: {len(cards)} produtos")

    lista = list(produtos.values())
    com_categoria = sum(p.categoria_grupo != "Não classificado" for p in lista)
    com_marca = sum(p.marca != "Não identificada" for p in lista)
    relator.log(
        f"Categoria identificada para {com_categoria}/{len(lista)} e marca para {com_marca}/{len(lista)} produtos",
        "ok",
    )
    return lista
