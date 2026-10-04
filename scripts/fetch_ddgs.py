"""fetch_ddgs.py — precio semanal de DDGS FOB Vessel Gulf (New Orleans) desde USDA AMS.

Fuente: USDA AMS "National Weekly Ethanol Report" (AMS_3616), tabla "Distillers Grain
Dried 10%", subsección "Export Point", fila "New Orleans ... FOB - OV" (OV = Ocean
Vessel). Ejemplo de fila tal como sale de `pdftotext -layout`:

    New Orleans    Ask    245.00-260.00    DN 5.00    254.50    191.67    FOB - OV    Current
                          (mín-máx)        (cambio)   (promedio)(año atrás)

Mapeo a la serie (contrato del dashboard): close = promedio, high = máximo del rango,
low = mínimo del rango, fecha = último día de la semana del reporte ("Report for
9/28/2026 - 10/2/2026" -> 2026-10-02).

Dos modos:
  python scripts/fetch_ddgs.py              -> baja el reporte vigente (URL fija que USDA
                                               sobrescribe cada semana) y lo fusiona.
  python scripts/fetch_ddgs.py --historico  -> recorre el archivo ESMIS de USDA (todos los
                                               AMS_3616 desde el primero, del 22-jul-2022)
                                               y los fusiona.

El reporte AMS_3616 existe desde julio de 2022. Antes de eso USDA no publicaba un precio
"FOB Vessel" para el Golfo (el reporte diario antiguo traía "CIF NOLA", que es otra base
de precio), así que esta serie empieza el 2022-07-22 y NO se rellena hacia atrás.

Reglas de integridad (ver CLAUDE.md): un dato que no se puede leer con certeza se reporta
y se descarta, nunca se convierte en 0 ni se aproxima. La serie se fusiona por fecha y
nunca se reemplaza completa. Este script es independiente de fetch_and_update.py: si
USDA cambia su formato, falla solo esto y el pipeline de Yahoo sigue igual.

Requiere `pdftotext` (paquete poppler-utils).
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
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
DOC_PATH = ROOT / "data" / "historia" / "ddgs_fob_gulf.json"

URL_VIGENTE = "https://www.ams.usda.gov/mnreports/ams_3616.pdf"
ESMIS = "https://esmis.nal.usda.gov"
ESMIS_LISTADO = ESMIS + "/publication/national-weekly-ethanol-report?page={page}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Rango de plausibilidad en USD/ton corta. DDGS en el Golfo ha estado entre ~150 y ~350
# en la última década; esto solo atrapa errores de lectura groseros (p. ej. un 0, o un
# número de otra columna), no pretende juzgar el mercado.
PRECIO_MIN, PRECIO_MAX = 50.0, 1000.0

META = {
    "id": "ddgs_fob_gulf",
    "nombre": "DDGS FOB Golfo (buque)",
    "ticker": "USDA AMS_3616",
    "unidad": "USD/ton corta",
    "dec": 2,
    "freq": "semanal",
    "cadencia": "Semanal",
    "exchange": "USDA AMS",
    "contrato": "Distillers Grain Dried 10%, New Orleans, FOB Ocean Vessel",
    "fuente": "USDA AMS National Weekly Ethanol Report (AMS_3616)",
    "fuente_url": URL_VIGENTE,
}


class FormatoInesperado(Exception):
    """El PDF no tiene la forma esperada. Nunca se adivina: se reporta y se descarta."""


def descargar(url, intentos=3):
    ultimo_error = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo_error = e
            time.sleep(2 * (i + 1))
    raise ultimo_error


def pdf_a_texto(pdf_bytes):
    if not pdf_bytes.startswith(b"%PDF"):
        raise FormatoInesperado("la descarga no es un PDF")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "r.pdf"
        pdf.write_bytes(pdf_bytes)
        out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                             capture_output=True, check=True)
    return out.stdout.decode("utf-8", "replace")


def _num(s):
    return float(s.replace(",", ""))


def parse_reporte(texto):
    """Devuelve el punto {fecha, close, high, low} de New Orleans FOB - OV, o lanza
    FormatoInesperado explicando qué no calzó."""
    m = re.search(r"Report for\s+(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if not m:
        raise FormatoInesperado("no se encontró la línea 'Report for M/D/AAAA - M/D/AAAA'")
    fecha = dt.date(int(m.group(6)), int(m.group(4)), int(m.group(5)))

    # Solo dentro de la tabla de DDGS seco: desde "Distillers Grain Dried" hasta la
    # siguiente tabla de "Distillers Grain" (Modified Wet / Wet) o el fin del texto.
    ini = texto.find("Distillers Grain Dried")
    if ini < 0:
        raise FormatoInesperado("no se encontró la tabla 'Distillers Grain Dried'")
    fin = texto.find("Distillers Grain", ini + len("Distillers Grain Dried"))
    seccion = texto[ini: fin if fin > 0 else len(texto)]

    exp = seccion.find("Export Point")
    if exp < 0:
        raise FormatoInesperado("la tabla de DDGS seco no tiene subsección 'Export Point'")

    filas = [l for l in seccion[exp:].splitlines() if l.strip().startswith("New Orleans")]
    # pdftotext a veces repite una línea idéntica; se ignoran duplicados exactos.
    filas = list(dict.fromkeys(l.strip() for l in filas))
    filas_ov = [l for l in filas if re.search(r"FOB\s*-\s*OV\b", l)]
    if len(filas_ov) != 1:
        raise FormatoInesperado(f"se esperaba 1 fila 'New Orleans ... FOB - OV', hay {len(filas_ov)}: {filas}")

    campos = re.split(r"\s{2,}", filas_ov[0])
    i_flete = next((i for i, c in enumerate(campos) if re.fullmatch(r"FOB\s*-\s*OV", c)), None)
    if i_flete is None or len(campos) < 4:
        raise FormatoInesperado(f"fila con columnas inesperadas: {campos}")

    rango = campos[2]
    mr = re.fullmatch(r"(\d[\d,]*\.\d+)(?:\s*-\s*(\d[\d,]*\.\d+))?", rango)
    if not mr:
        raise FormatoInesperado(f"la columna de precio no es 'mín-máx' ni un número: {rango!r}")
    low = _num(mr.group(1))
    high = _num(mr.group(2)) if mr.group(2) else low

    # Entre el precio y el flete vienen: [cambio (texto: UNCH/UP/DN), si hay]
    # [promedio] [año atrás, si hay]. Los numéricos puros son promedio y año atrás.
    numericos = [c for c in campos[3:i_flete] if re.fullmatch(r"\d[\d,]*\.\d+", c)]
    if not numericos:
        raise FormatoInesperado(f"no se encontró la columna 'Average': {campos}")
    promedio = _num(numericos[0])

    for v in (low, high, promedio):
        if not (PRECIO_MIN <= v <= PRECIO_MAX):
            raise FormatoInesperado(f"precio fuera de rango plausible ({v}): {campos}")
    if low > high:
        raise FormatoInesperado(f"mínimo mayor que máximo: {campos}")

    advertencia = None
    if not (low <= promedio <= high):
        # Igual que sanitize_high_low() del pipeline de Yahoo: nunca se toca close,
        # solo se ensancha el rango con el propio promedio, y se avisa.
        advertencia = f"{fecha}: promedio {promedio} fuera de [{low}, {high}]; se ensancha el rango"
        low, high = min(low, promedio), max(high, promedio)

    return {"fecha": fecha.isoformat(), "close": promedio, "high": high, "low": low}, advertencia


def links_esmis():
    """Todos los AMS_3616.PDF del archivo ESMIS (más nuevo primero), sin duplicados."""
    vistos, links, page = set(), [], 0
    while True:
        h = descargar(ESMIS_LISTADO.format(page=page)).decode("utf-8", "replace")
        nuevos = [html.unescape(l) for l in
                  re.findall(r'href="(/sites/default/release-files/[^"]+AMS_3616\.PDF)"', h, re.I)]
        nuevos = [l for l in nuevos if l not in vistos]
        if not nuevos:
            break
        for l in nuevos:
            vistos.add(l)
            links.append(ESMIS + l)
        page += 1
        if page > 500:
            raise RuntimeError("el listado de ESMIS no termina; revisar paginación")
    return links


def cargar_doc():
    if DOC_PATH.exists():
        with open(DOC_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {**META, "serie": []}


def merge(serie, nuevos):
    """Fusión por fecha: el último valor gana; nunca se reemplaza la serie completa.
    No se recorta: el histórico semanal es chico (~52 puntos/año)."""
    by_fecha = {p["fecha"]: p for p in serie}
    for p in nuevos:
        by_fecha[p["fecha"]] = p
    return sorted(by_fecha.values(), key=lambda p: p["fecha"])


def main():
    historico = "--historico" in sys.argv[1:]
    advertencias, nuevos = [], []

    if historico:
        urls = links_esmis()
        print(f"ESMIS: {len(urls)} reportes AMS_3616 encontrados")
    else:
        urls = [URL_VIGENTE]

    for url in urls:
        try:
            punto, adv = parse_reporte(pdf_a_texto(descargar(url)))
        except (FormatoInesperado, urllib.error.URLError, TimeoutError,
                subprocess.CalledProcessError) as e:
            advertencias.append(f"{url}: {e} — se descarta, no se inventa nada")
            continue
        if adv:
            advertencias.append(adv)
        nuevos.append(punto)
        if historico:
            print(f"  {punto['fecha']}  close={punto['close']:.2f}  [{punto['low']:.2f}-{punto['high']:.2f}]")

    # Si el mismo fin de semana aparece en dos archivos (p. ej. una corrección), gana el
    # publicado más tarde. ESMIS lista del más nuevo al más viejo, así que se invierte.
    if historico:
        nuevos.reverse()

    doc = cargar_doc()
    serie_antes = doc.get("serie", [])
    serie = merge(serie_antes, nuevos)
    for k, v in META.items():
        doc[k] = v

    if serie != serie_antes:
        doc["serie"] = serie
        doc["ultima_actualizacion"] = dt.datetime.now(ZoneInfo("America/Santiago")).isoformat(timespec="seconds")
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DOC_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        u = serie[-1]
        print(f"DDGS FOB Golfo: n={len(serie)} desde {serie[0]['fecha']} último={u['fecha']} close={u['close']}")
    else:
        print("Sin cambios: el reporte vigente ya estaba en la serie.")

    if advertencias:
        print("\nAdvertencias de esta corrida:")
        for a in advertencias:
            print(" -", a)
    # Falla en voz alta (job en rojo en Actions) si no se pudo leer nada, para que se note.
    if not nuevos:
        sys.exit("ERROR: no se pudo leer ningún reporte de DDGS; la serie quedó como estaba.")


if __name__ == "__main__":
    main()
