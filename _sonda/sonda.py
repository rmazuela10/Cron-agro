"""Sonda temporal 4: fecha del título de cada post vs fecha de creación del PDF (sin OCR)."""
import re, subprocess, sys, tempfile, datetime as dt
sys.path.insert(0, "scripts")
import fetch_ddgs as f
for page in range(1, 29):
    for u in f.posts_de_pagina(page):
        try:
            fecha, pdf = f.leer_post(u)
            with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
                t.write(f.descargar(pdf)); t.flush()
                info = subprocess.run(["pdfinfo", t.name], capture_output=True, text=True).stdout
            m = re.search(r"CreationDate:\s+\w+ (\w+)\s+(\d+) [\d:]+ (\d{4})", info)
            c = dt.datetime.strptime(" ".join(m.groups()), "%b %d %Y").date() if m else None
            d = (c - fecha).days if c else None
            print(f"{'RARO' if d is None or abs(d) > 10 else 'ok  '} titulo={fecha} pdf_creado={c} dif={d} {pdf}", flush=True)
        except Exception as e:
            print("ERR", u, e)
