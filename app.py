# -*- coding: utf-8 -*-
"""
app.py
------
Abre a interface gráfica do PriceBot.

Jeito mais fácil: dê dois cliques em "Iniciar.bat" (ele cria a venv e
instala tudo na primeira vez). Ou, com a venv ativada:

    python app.py
"""

from robo_precos.gui.app import iniciar

if __name__ == "__main__":
    iniciar()
