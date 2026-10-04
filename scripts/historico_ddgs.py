"""historico_ddgs.py — construye el histórico semanal de DDGS FOB Vessel Gulf desde enero
de 2021 en data/historia/ddgs_fob_gulf.json, recorriendo el listado de reportes semanales
de USGC (https://grains.org/ddgs_report/) y leyendo la tabla de la página 2 de cada PDF.

Mismo formato JSON que las demás variables del repo, pero cada punto lleva solo
{fecha, close} (sin high ni low). La forma de leer cada reporte, y las validaciones,
están en fetch_ddgs.py.

Se puede correr de nuevo cuando se quiera: solo agrega las semanas que faltan. Con
--rehacer vuelve a leer todas las semanas (las existentes se sobrescriben por fecha).
Uso:  python scripts/historico_ddgs.py [--rehacer]
"""
import datetime as dt
import os
import sys
import urllib.error

from fetch_ddgs import actualizar, posts_de_pagina, terminar

DESDE = dt.date(2021, 1, 1)
HILOS = os.cpu_count() or 2  # PDFs leídos a la vez (el OCR es lento)


def main():
    rehacer = "--rehacer" in sys.argv[1:]
    advertencias, leidos, page = [], 0, 1
    while True:
        try:
            posts = posts_de_pagina(page)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break  # se acabó el listado
            raise
        if not posts:
            break
        print(f"Listado página {page}: {len(posts)} reportes", flush=True)
        n, mas_antigua = actualizar(posts, advertencias, desde=DESDE,
                                    solo_faltantes=not rehacer, verbose=True,
                                    hilos=HILOS)
        leidos += n
        if mas_antigua and mas_antigua < DESDE:
            break  # ya llegamos a 2020: no se va más atrás
        page += 1
    terminar(advertencias, leidos)


if __name__ == "__main__":
    main()
