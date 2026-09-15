# -*- coding: utf-8 -*-
"""
config.py
---------
Configurações centrais do robô. Edite os valores abaixo se quiser
personalizar (textos da interface, pasta de saída, dados de cadastro...).
"""

from pathlib import Path

# --------------------------------------------------------------------------
# 1) IDENTIDADE DA APLICAÇÃO (aparece na interface — personalize à vontade)
# --------------------------------------------------------------------------
APP_NOME = "PriceBot"
APP_SUBTITULO = "Robô de análise de preços"
ASSINATURA_RODAPE = "Automações & Facilitadores"

# --------------------------------------------------------------------------
# 2) SITE
# --------------------------------------------------------------------------
BASE_URL = "https://automationexercise.com"
LOGIN_URL = f"{BASE_URL}/login"
PRODUCTS_URL = f"{BASE_URL}/products"

# --------------------------------------------------------------------------
# 3) ARQUIVOS LOCAIS
#    Tudo é relativo à pasta do projeto, então funciona em qualquer máquina.
# --------------------------------------------------------------------------
PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_SAIDA = PASTA_PROJETO / "saida"
PASTA_ASSETS = PASTA_PROJETO / "assets"
ARQUIVO_COFRE = PASTA_PROJETO / "dados" / "cofre.db"   # contas criptografadas (ver cofre.py)
ARQUIVO_ULTIMA_COLETA = PASTA_SAIDA / "ultima_coleta.json"
PREFIXO_ARQUIVO_EXCEL = "precos_automationexercise"

# --------------------------------------------------------------------------
# 4) DADOS DE CADASTRO usados SOMENTE se for preciso criar uma conta nova.
#    São dados fictícios válidos para o formulário do site de treinamento.
# --------------------------------------------------------------------------
DADOS_CADASTRO = {
    "titulo": "Mr",              # "Mr" ou "Mrs"
    "nome": "Robo",
    "sobrenome": "Precos",
    "dia_nascimento": "15",
    "mes_nascimento": "6",
    "ano_nascimento": "1990",
    "newsletter": True,
    "ofertas_especiais": True,
    "endereco1": "Rua de Teste, 123",
    "endereco2": "",
    "pais": "India",
    "estado": "SP",
    "cidade": "Sao Paulo",
    "cep": "01000-000",
    "telefone": "11999999999",
}

# --------------------------------------------------------------------------
# 5) COMPORTAMENTO DO NAVEGADOR (Playwright)
# --------------------------------------------------------------------------
HEADLESS = True           # a interface permite trocar isso por um switch
TIMEOUT_PADRAO_MS = 20_000
SLOW_MO_MS = 0            # usado quando o navegador está visível: 120

# Requisições para esses domínios são bloqueadas: o site de treino é cheio
# de anúncios que deixam a navegação lenta e abrem pop-ups por cima da página.
DOMINIOS_BLOQUEADOS = (
    "googlesyndication.com",
    "doubleclick.net",
    "googleadservices.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googletagservices.com",
    "adservice.google",
    "fundingchoicesmessages.google.com",
    "amazon-adsystem.com",
    "adsbygoogle",
)
