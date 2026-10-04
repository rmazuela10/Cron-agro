"""Sonda temporal 2: (1) todos los enlaces del listado de las páginas 8-12 (hueco oct-2024 a
ene-2025); (2) baja PDFs de semanas rechazadas, sospechosas y una muestra aleatoria aceptada."""
import os, re, sys, random, json
sys.path.insert(0, "scripts")
import fetch_ddgs as f
os.makedirs("_sonda/pdfs2", exist_ok=True)
for page in range(8, 13):
    h = f.descargar(f.LISTADO_PAGINA.format(page=page)).decode("utf-8", "replace")
    links = list(dict.fromkeys(re.findall(r'href="([^"]+)"', h)))
    print(f"== pagina {page}")
    for l in links:
        if "ddgs" in l.lower() or "?p=" in l:
            print("  ", l)
quiero = """weekly-ddgs-market-report-september-17-2026 weekly-ddgs-market-report-september-10-2026
ddgs-weekly-market-report-january-16-2025 ddgs-weekly-market-report-october-3-2024
ddgs-weekly-market-report-september-26-2024 ddgs-weekly-market-report-january-18-2024
ddgs-weekly-market-report-june-23-2022 ddgs-weekly-market-report-may-26-2022
ddgs-weekly-market-report-july-22-2021 ddgs-weekly-market-report-october-9-2025""".split()
urls = [f"https://grains.org/ddgs_report/{q}/" for q in quiero]
# sospechosas y muestra aleatoria de aceptadas
serie = {p["fecha"] for p in json.load(open("data/historia/ddgs_fob_gulf.json"))["serie"]}
todos = []
for page in range(1, 29):
    todos += f.posts_de_pagina(page)
random.seed(7)
extra = random.sample(todos, 16)
for u in urls + extra:
    try:
        fecha, pdf = f.leer_post(u)
        tag = "acep" if str(fecha) in serie else "rech"
        open(f"_sonda/pdfs2/{fecha}_{tag}.pdf", "wb").write(f.descargar(pdf)); print(fecha, tag, pdf)
    except Exception as e:
        print("ERR", u, e)
for u in todos:
    if any(k in u for k in ("july-8-2021", "july-1-2021", "march-17-2022", "september-24-2026")):
        try:
            fecha, pdf = f.leer_post(u)
            open(f"_sonda/pdfs2/{fecha}_sosp.pdf", "wb").write(f.descargar(pdf)); print(fecha, "sosp", pdf)
        except Exception as e:
            print("ERR", u, e)
print("total posts listados:", len(todos), len(set(todos)))
