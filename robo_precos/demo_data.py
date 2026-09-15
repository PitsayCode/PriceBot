# -*- coding: utf-8 -*-
"""
demo_data.py
------------
Catálogo FICTÍCIO usado pelo modo demonstração (sem acessar o site).
Imita o formato do automationexercise.com para gravar vídeos e testar o
layout do Excel/interface offline.
"""

from __future__ import annotations

from dataclasses import replace

from . import config
from .modelos import Produto

# (id, nome, marca, grupo, subcategoria, preço)
_CATALOGO = [
    ("1", "Blue Top", "Polo", "Women", "Tops", 500),
    ("2", "Men Tshirt", "H&M", "Men", "Tshirts", 400),
    ("3", "Sleeveless Dress", "Madame", "Women", "Dress", 1000),
    ("4", "Stylish Dress", "Madame", "Women", "Dress", 1500),
    ("5", "Winter Top", "Mast & Harbour", "Women", "Tops", 600),
    ("6", "Summer White Top", "H&M", "Women", "Tops", 400),
    ("7", "Madame Top For Women", "Madame", "Women", "Tops", 1000),
    ("8", "Fancy Green Top", "Polo", "Women", "Tops", 700),
    ("11", "Blue Cotton Indie Mickey Dress", "Babyhug", "Kids", "Dress", 600),
    ("12", "Long Maxi Tulle Fancy Dress Up Outfits For Girls", "Babyhug", "Kids", "Dress", 1400),
    ("13", "Sleeveless Unicorn Patch Gown - Pink", "Allen Solly Junior", "Kids", "Dress", 1050),
    ("14", "Cotton Mull Embroidered Dress", "Allen Solly Junior", "Kids", "Dress", 1100),
    ("16", "Sleeves Top and Short - Blue & Pink", "Kookie Kids", "Kids", "Tops & Shirts", 478),
    ("18", "Little Girls Mr. Panda Shirt", "Babyhug", "Kids", "Tops & Shirts", 543),
    ("19", "Sleeveless Unicorn Print Fit & Flare Net Dress", "Allen Solly Junior", "Kids", "Dress", 1100),
    ("20", "Cotton Silk Hand Block Print Saree", "Biba", "Women", "Saree", 3000),
    ("21", "Rust Red Linen Saree", "Biba", "Women", "Saree", 3500),
    ("22", "Beautiful Peacock Blue Cotton Linen Saree", "Biba", "Women", "Saree", 5000),
    ("23", "Lace Top For Women", "Mast & Harbour", "Women", "Tops", 1400),
    ("24", "Colour Blocked Shirt – Sky Blue", "Kookie Kids", "Kids", "Tops & Shirts", 1389),
    ("28", "Pure Cotton V-Neck T-Shirt", "Polo", "Men", "Tshirts", 1299),
    ("29", "Green Side Placket Detail T-Shirt", "Polo", "Men", "Tshirts", 1000),
    ("30", "Premium Polo T-Shirts", "Polo", "Men", "Tshirts", 1500),
    ("31", "Pure Cotton Neon Green Tshirt", "H&M", "Men", "Tshirts", 850),
    ("33", "Soft Stretch Jeans", "H&M", "Men", "Jeans", 799),
    ("35", "Regular Fit Straight Jeans", "Mast & Harbour", "Men", "Jeans", 1200),
    ("37", "Grunt Blue Slim Fit Jeans", "H&M", "Men", "Jeans", 1400),
    ("38", "Rose Pink Embroidered Maxi Dress", "Madame", "Women", "Dress", 1200),
    ("40", "Half Sleeves Printed Frock", "Babyhug", "Kids", "Dress", 720),
    ("41", "Frozen Tops For Kids", "Kookie Kids", "Kids", "Tops & Shirts", 278),
    ("42", "Full Sleeves Top Cherry - Pink", "Kookie Kids", "Kids", "Tops & Shirts", 679),
    ("43", "Graphic Design Men T Shirt - Blue", "Polo", "Men", "Tshirts", 1389),
]

_PRODUTOS = [
    Produto(
        id_produto=pid,
        nome=nome,
        preco_valor=float(preco),
        moeda="Rs.",
        preco_texto=f"Rs. {preco}",
        marca=marca,
        categoria_grupo=grupo,
        categoria_sub=sub,
        url=f"{config.BASE_URL}/product_details/{pid}",
    )
    for pid, nome, marca, grupo, sub, preco in _CATALOGO
]


def produtos_demo() -> list[Produto]:
    """Cópias novas a cada chamada (quem usar pode alterar à vontade)."""
    return [replace(p) for p in _PRODUTOS]
