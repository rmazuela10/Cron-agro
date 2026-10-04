"""fetch_ddgs.py — precio semanal de DDGS FOB Vessel Gulf desde el reporte semanal de DDGS
del U.S. Grains & BioProducts Council (USGC): https://grains.org/ddgs_report/

Cada semana USGC publica un post con un PDF ("Download report"). En la página 2 del PDF
viene la "DDGS Price Table" (USD/ton métrica, fuente World Perspectives, Inc.), con una
fila "FOB Vessel GULF" y tres columnas: el mes más cercano y los dos siguientes. Ejemplo
(reporte del 6-feb-2025):

    Delivery Point            February   March   April
    FOB Vessel GULF              218       215     212

Se guarda el precio del mes más cercano (la primera columna), que es la oferta vigente esa
semana. Cada punto es {fecha, close}: fecha = fecha del reporte (la del título del post) y
close = ese precio. Por decisión de Ramon la serie guarda solo el cierre, sin high ni low.

La tabla es una IMAGEN dentro del PDF (no trae texto), así que se lee con OCR (tesseract):
ver ocr_tabla.py. Para no aceptar una lectura dudosa, la fila se lee de muchas formas
independientes y se exige consenso (la misma lectura de los tres valores en al menos 3
lecturas y en al menos 3/4 de las lecturas válidas). Además cada valor debe estar en un
rango plausible y los tres meses no pueden diferir más de un 20% entre sí. Si algo no
calza, ese reporte se descarta y se avisa: nunca se adivina ni se convierte en 0 (ver
reglas en CLAUDE.md).

Uso:
  python scripts/fetch_ddgs.py      -> lee los reportes más recientes (primera página del
                                       listado) y los fusiona. Lo corre el cron diario.
  python scripts/historico_ddgs.py  -> construye el histórico desde enero de 2021.

Este script es independiente de fetch_and_update.py: si USGC cambia su formato, falla solo
esto y el pipeline de Yahoo sigue igual.

Requiere poppler-utils, tesseract-ocr, Pillow y numpy.
"""
import datetime as dt
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import ocr_tabla

ROOT = Path(__file__).parent.parent
DOC_PATH = ROOT / "data" / "historia" / "ddgs_fob_gulf.json"

LISTADO = "https://grains.org/ddgs_report/"
LISTADO_PAGINA = LISTADO + "page/{page}/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Rango de plausibilidad en USD/ton métrica. DDGS FOB Golfo ha estado entre ~180 y ~400
# desde 2021; esto solo atrapa errores de lectura groseros, no pretende juzgar el mercado.
PRECIO_MIN, PRECIO_MAX = 100, 700
DIFERENCIA_MAX_ENTRE_MESES = 0.20

MESES = ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"]

META = {
    "id": "ddgs_fob_gulf",
    "nombre": "DDGS FOB Golfo (buque)",
    "ticker": "USGC DDGS Price Table",
    "unidad": "USD/ton métrica",
    "dec": 0,
    "freq": "semanal",
    "cadencia": "Semanal",
    "exchange": "USGC / World Perspectives",
    "contrato": "FOB Vessel GULF, mín. 35% proteína+grasa, oferta del mes más cercano",
    "fuente": "U.S. Grains & BioProducts Council, Weekly DDGS Market Report (tabla de la pág. 2)",
    "fuente_url": LISTADO,
}


class FormatoInesperado(Exception):
    """El reporte no tiene la forma esperada. Nunca se adivina: se reporta y se descarta."""


def descargar(url, intentos=4):
    ultimo_error = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise  # 404 y similares no se arreglan reintentando
            ultimo_error = e
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo_error = e
        time.sleep(5 * (i + 1))
    raise ultimo_error


# --- Listado y posts ----------------------------------------------------------------------

def posts_de_pagina(page):
    """URLs de los posts de una página del listado (del más nuevo al más viejo)."""
    url = LISTADO if page == 1 else LISTADO_PAGINA.format(page=page)
    h = descargar(url).decode("utf-8", "replace")
    urls = re.findall(r'href="(https://grains\.org/ddgs_report/[^"/#?]+/)"', h)
    return [u for u in dict.fromkeys(urls) if not u.endswith(("/feed/",)) and "/page/" not in u]


def fecha_de_titulo(titulo):
    """'DDGS Weekly Market Report – August 20,2026' -> date(2026, 8, 20)."""
    m = re.search(r"(" + "|".join(MESES) + r")\.?\s+(\d{1,2})\s*,\s*(\d{4})", titulo, re.I)
    if not m:
        raise FormatoInesperado(f"no se encontró una fecha en el título: {titulo!r}")
    return dt.date(int(m.group(3)), MESES.index(m.group(1).lower()) + 1, int(m.group(2)))


def leer_post(url):
    """Devuelve (fecha_del_reporte, url_del_pdf)."""
    h = descargar(url).decode("utf-8", "replace")
    t = re.search(r"<title>(.*?)</title>", h, re.S)
    if not t:
        raise FormatoInesperado("el post no tiene <title>")
    fecha = fecha_de_titulo(html.unescape(t.group(1)))
    pdfs = list(dict.fromkeys(re.findall(r'href="(https://grains\.org/wp-content/uploads/[^"]+\.pdf)"', h, re.I)))
    if not pdfs:
        raise FormatoInesperado("el post no enlaza ningún PDF")
    return fecha, html.unescape(pdfs[0])


# --- Lectura de la tabla (OCR) ------------------------------------------------------------

# Consenso exigido entre las lecturas OCR válidas de la fila (ver ocr_tabla.py): la lectura
# ganadora necesita al menos 3 votos y al menos 3/4 de las lecturas válidas.
VOTOS_MIN, CONSENSO_MIN = 3, 0.75


def _a_valores(lectura):
    return [None if t == "N/A" else int(t) for t in lectura]


def _plausible(valores):
    if len(valores) != 3 or valores[0] is None:
        return False
    numeros = [v for v in valores if v is not None]
    return (all(PRECIO_MIN <= v <= PRECIO_MAX for v in numeros)
            and max(numeros) <= min(numeros) * (1 + DIFERENCIA_MAX_ENTRE_MESES))


def leer_tabla(pdf_bytes):
    """Devuelve (precio_mes_cercano, [los tres valores]) o lanza FormatoInesperado."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise FormatoInesperado("la descarga no es un PDF")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "r.pdf"
        pdf.write_bytes(pdf_bytes)
        # La tabla va en la página 2; por si algún reporte la movió, se prueba 1 y 3 después.
        for pagina in (2, 1, 3):
            todas = ocr_tabla.lecturas(pdf, pagina)
            if todas:
                break
        else:
            raise FormatoInesperado("no se encontró la fila 'FOB Vessel GULF' en las páginas 1-3")

    validas = [tuple(_a_valores(l)) for l in todas
               if len(l) == 3 and all(ocr_tabla.NUM.match(t) for t in l)]
    validas = [v for v in validas if _plausible(list(v))]
    if not validas:
        raise FormatoInesperado(f"ninguna lectura OCR válida de la fila: {todas}")
    ganadora, votos = Counter(validas).most_common(1)[0]
    if votos < VOTOS_MIN or votos / len(validas) < CONSENSO_MIN:
        raise FormatoInesperado(f"sin consenso entre lecturas OCR: {Counter(validas).most_common(4)}")
    return ganadora[0], list(ganadora)


# --- Serie --------------------------------------------------------------------------------

def cargar_doc():
    if DOC_PATH.exists():
        with open(DOC_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {**META, "serie": []}


def merge(serie, nuevos):
    """Fusión por fecha: el último valor gana; nunca se reemplaza la serie completa.
    No se recorta: el histórico semanal es chico (~52 puntos/año)."""
    by_fecha = {p["fecha"]: {"fecha": p["fecha"], "close": p["close"]} for p in serie}
    for p in nuevos:
        by_fecha[p["fecha"]] = p
    return sorted(by_fecha.values(), key=lambda p: p["fecha"])


def actualizar(posts, advertencias, desde=None, solo_faltantes=True, verbose=False):
    """Lee cada post de `posts`, saca el precio y lo fusiona en el JSON. Si `desde` viene,
    se ignoran los reportes anteriores a esa fecha; con `solo_faltantes` se saltan las
    semanas que ya están en la serie. Devuelve (leídos, fecha_más_antigua)."""
    ya = {p["fecha"] for p in cargar_doc().get("serie", [])} if solo_faltantes else set()
    nuevos, mas_antigua = [], None
    for url in posts:
        try:
            fecha, pdf_url = leer_post(url)
            mas_antigua = min(mas_antigua or fecha, fecha)
            if (desde and fecha < desde) or fecha.isoformat() in ya:
                continue
            precio, fila = leer_tabla(descargar(pdf_url))
        except (FormatoInesperado, urllib.error.URLError, TimeoutError,
                subprocess.CalledProcessError) as e:
            advertencias.append(f"{url}: {e} — se descarta, no se inventa nada")
            continue
        nuevos.append({"fecha": fecha.isoformat(), "close": precio})
        if verbose:
            print(f"  {fecha}  close={precio}  fila={fila}", flush=True)

    doc = cargar_doc()
    serie_antes = doc.get("serie", [])
    serie = merge(serie_antes, nuevos)
    if serie != serie_antes or any(doc.get(k) != v for k, v in META.items()):
        doc.update(META)
        doc["serie"] = serie
        doc["ultima_actualizacion"] = dt.datetime.now(ZoneInfo("America/Santiago")).isoformat(timespec="seconds")
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DOC_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        if serie:
            u = serie[-1]
            print(f"DDGS FOB Golfo: n={len(serie)} desde {serie[0]['fecha']} último={u['fecha']} close={u['close']}")
    else:
        print("Sin cambios: los reportes ya estaban en la serie.")
    return len(nuevos), mas_antigua


def terminar(advertencias, leidos):
    if advertencias:
        print("\nAdvertencias de esta corrida:")
        for a in advertencias:
            print(" -", a)
    # Falla en voz alta (job en rojo en Actions) si no se pudo leer nada, para que se note.
    if not leidos:
        sys.exit("ERROR: no se pudo leer ningún reporte de DDGS; la serie quedó como estaba.")


def main():
    advertencias = []
    # Los posts de la primera página (las últimas ~10 semanas): así, si una corrida falló,
    # la siguiente recupera la semana perdida.
    posts = posts_de_pagina(1)
    leidos, _ = actualizar(posts, advertencias)
    if advertencias:
        print("\nAdvertencias de esta corrida:")
        for a in advertencias:
            print(" -", a)
    # Falla en voz alta si no se pudo leer el reporte más reciente (y no estaba ya cargado).
    doc = cargar_doc()
    if any(a.startswith(posts[0]) for a in advertencias):
        sys.exit("ERROR: no se pudo leer el reporte más reciente de DDGS; revisar el log.")
    print(f"OK: {leidos} semana(s) nueva(s); último dato {doc['serie'][-1] if doc.get('serie') else 'ninguno'}")


if __name__ == "__main__":
    main()
