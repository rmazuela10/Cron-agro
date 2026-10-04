"""Sonda temporal: recorta la fila FOB Vessel GULF de algunos PDF para revisar a mano."""
import json, random, subprocess, sys, os
sys.path.insert(0, "scripts")
import fetch_ddgs as f
os.makedirs("_sonda/out", exist_ok=True)
serie = json.load(open("data/historia/ddgs_fob_gulf.json"))["serie"]
print("n =", len(serie), serie[0], serie[-1])
posts = []
for page in (1, 8, 16, 24, 30):
    posts += f.posts_de_pagina(page)[:1]
for i, u in enumerate(posts):
    fecha, pdf = f.leer_post(u)
    open("/tmp/r.pdf", "wb").write(f.descargar(pdf))
    subprocess.run(["pdftoppm", "-f", "2", "-l", "2", "-r", "60", "-png", "/tmp/r.pdf", f"_sonda/out/{fecha}"])
    print(fecha, [p for p in serie if p["fecha"] == fecha.isoformat()])
