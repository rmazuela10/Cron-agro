"""Sonda temporal: baja una muestra de PDFs de USGC (2021-2026) para probar la lectura."""
import os, sys
sys.path.insert(0, "scripts")
import fetch_ddgs as f
os.makedirs("_sonda/pdfs", exist_ok=True)
for page in (1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28):
    for u in f.posts_de_pagina(page)[:2]:
        try:
            fecha, pdf = f.leer_post(u)
            open(f"_sonda/pdfs/{fecha}.pdf", "wb").write(f.descargar(pdf)); print(fecha, pdf)
        except Exception as e:
            print("ERR", u, e)
