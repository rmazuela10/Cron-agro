"""Sonda temporal 3: baja los PDFs de las semanas que se agregaron en la segunda pasada."""
import os, sys
sys.path.insert(0, "scripts")
import fetch_ddgs as f
os.makedirs("_sonda/pdfs3", exist_ok=True)
quiero = set(open("_sonda/nuevas.txt").read().split())
for page in range(1, 29):
    for u in f.posts_de_pagina(page):
        try:
            fecha, pdf = f.leer_post(u)
            if str(fecha) in quiero:
                open(f"_sonda/pdfs3/{fecha}.pdf", "wb").write(f.descargar(pdf)); print(fecha, pdf)
        except Exception as e:
            print("ERR", u, e)
