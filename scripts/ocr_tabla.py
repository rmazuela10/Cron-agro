"""ocr_tabla.py — lee la fila "FOB Vessel GULF" de la "DDGS Price Table" de USGC.

La tabla viene como IMAGEN dentro del PDF, y su diseño cambió con los años (con grilla y
encabezado naranjo en 2021-2023, filas sombreadas en 2024, sin grilla desde 2025). Por eso
no se confía en una sola lectura: se generan varias lecturas independientes de la misma
fila, combinando

  * dos fuentes de imagen: la página renderizada a 300 dpi y la imagen original de la
    tabla extraída del PDF (ampliada);
  * dos métodos: (a) ubicar las filas de 3 números, leer la etiqueta de cada una y quedarse
    con la que dice "FOB Vessel"; (b) leer la tabla completa como texto y buscar la línea
    que empieza con "FOB Vessel";
  * distintos umbrales de blanco/negro y tamaños.

Antes de leer se borran las líneas de la grilla (confunden al OCR) y, si una zona tiene
fondo oscuro con letra blanca, se invierte.

lecturas(pdf_path, pagina) devuelve la lista de lecturas (tuplas de 3 textos, p. ej.
('218', '215', '212') o ('298', 'N/A', '302')). Quien la usa decide si hay consenso
suficiente: este módulo no elige ni corrige nada.

Requiere pdftoppm/pdfimages (poppler-utils), tesseract (tesseract-ocr), Pillow y numpy.
"""
import csv
import io
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

NUM = re.compile(r"^(\d{3}|N/?A)$", re.I)
ETIQUETA = re.compile(r"F\w{0,2}\s*Ves+[eo]l", re.I)
SOLO_NUMEROS = ("-c", "tessedit_char_whitelist=0123456789N/A ")


def _tesseract(img, psm, extra=(), tsv=False):
    with tempfile.NamedTemporaryFile(suffix=".png") as t:
        img.save(t.name)
        cmd = ["tesseract", t.name, "-", "--psm", str(psm), *extra] + (["tsv"] if tsv else [])
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return out.decode("utf-8", "replace")


def _blanco_y_negro(img, umbral=150, borrar_grilla=True):
    """Blanco y negro; invierte si el fondo es oscuro; opcionalmente borra la grilla
    (filas/columnas que son negras en más de la mitad de su largo)."""
    a = np.array(img.convert("L"))
    if a.mean() < 110:
        a = 255 - a
    tinta = a < umbral
    if borrar_grilla:
        tinta[tinta.mean(axis=1) > 0.5, :] = False
        tinta[:, tinta.mean(axis=0) > 0.5] = False
    return Image.fromarray(np.where(tinta, 0, 255).astype("uint8"))


def _ancho_minimo(img, ancho):
    g = img.convert("L")
    if g.width < ancho:
        g = g.resize((ancho, int(g.height * ancho / g.width)), Image.LANCZOS)
    return g


def _tokens(texto):
    return tuple(t.upper().replace("NA", "N/A").replace("N//A", "N/A")
                 for t in re.findall(r"N/?A|\d+", texto, re.I))


def _filas_de_tres_numeros(img):
    """Filas que tienen exactamente 3 números (o N/A), según el TSV de tesseract."""
    filas = {}
    for w in csv.DictReader(io.StringIO(_tesseract(img, 6, tsv=True)), delimiter="\t",
                            quoting=csv.QUOTE_NONE):
        t = (w.get("text") or "").strip()
        if NUM.match(t):
            k = (w["block_num"], w["par_num"], w["line_num"])
            filas.setdefault(k, []).append((int(w["left"]), int(w["top"]), int(w["width"]),
                                            int(w["height"]), t.upper()))
    for toks in filas.values():
        if len(toks) == 3:
            toks.sort()
            top = min(t[1] for t in toks)
            bot = max(t[1] + t[3] for t in toks)
            yield top, bot, toks[0][0], toks[-1][0] + toks[-1][2], tuple(t[4] for t in toks)


def _metodo_filas(img):
    """(a) Ubica filas de 3 números, lee su etiqueta y relee los números de la fila
    FOB Vessel con OCR restringido a dígitos."""
    g = _ancho_minimo(img, 2000)
    limpia = _blanco_y_negro(g)
    lecturas = []
    for fuente in (limpia, g):
        for top, bot, x_num, x_fin, valores in _filas_de_tres_numeros(fuente):
            h = bot - top
            pad = int(h * 0.45)
            caja = (0, max(0, top - pad), max(1, x_num - h), bot + pad)
            etiquetas = (_tesseract(limpia.crop(caja), 7),
                         _tesseract(_blanco_y_negro(g.crop(caja), borrar_grilla=False), 7))
            if not any(ETIQUETA.search(e) for e in etiquetas):
                continue
            lecturas.append(valores)
            caja = (max(0, x_num - int(h * 0.6)), max(0, top - pad),
                    min(g.width, x_fin + int(h * 0.6)), bot + pad)
            for recorte in (limpia.crop(caja), _blanco_y_negro(g.crop(caja), borrar_grilla=False)):
                recorte = recorte.resize((recorte.width * 2, recorte.height * 2), Image.LANCZOS)
                lecturas.append(_tokens(_tesseract(recorte, 7, SOLO_NUMEROS)))
    return lecturas


def _metodo_texto(img):
    """(b) Lee la tabla completa como texto y toma la línea que empieza con FOB Vessel."""
    lecturas = []
    for ancho in (2000, 2800):
        g = _ancho_minimo(img, ancho)
        for umbral in (140, 180):
            for linea in _tesseract(_blanco_y_negro(g, umbral), 6).splitlines():
                m = re.search(r"F\w{0,2}\s*Ves+[eo]l\s*\S*\s+(.*)$", linea, re.I)
                if m:
                    lecturas.append(_tokens(m.group(1)))
        if img.width >= ancho:
            break  # la imagen ya era grande: ampliarla más no agrega información
    return lecturas


def _imagenes(pdf_path, pagina):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-f", str(pagina), "-l", str(pagina), "-r", "300", "-gray",
                        "-png", "-singlefile", str(pdf_path), f"{d}/p"], check=True, capture_output=True)
        yield Image.open(f"{d}/p.png").copy()
        subprocess.run(["pdfimages", "-f", str(pagina), "-l", str(pagina), "-png",
                        str(pdf_path), f"{d}/i"], check=True, capture_output=True)
        imagenes = [Image.open(p) for p in Path(d).glob("i-*.png")]
        if imagenes:
            # La tabla es la imagen más grande de la página (el resto son logos).
            yield max(imagenes, key=lambda i: i.width * i.height).copy()


def lecturas(pdf_path, pagina):
    todas = []
    for img in _imagenes(pdf_path, pagina):
        todas += _metodo_filas(img)
        todas += _metodo_texto(img)
    return todas
