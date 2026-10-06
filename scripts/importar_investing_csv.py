"""importar_investing_csv.py — fusiona en data/historia/<id>.json los CSV de "Datos históricos"
descargados A MANO desde Investing.com.

Investing no permite la descarga automática (responde con un control anti-robots y sus
términos lo prohíben), así que esta variable no se actualiza sola: Ramon descarga el CSV
cuando quiere y lo sube a data/manual/<id>/. El workflow importar-investing.yml corre este
script cada vez que aparece un archivo nuevo ahí.

Formato esperado (Investing en español; también se acepta el de la versión en inglés):
    "Fecha","Último","Apertura","Máximo","Mínimo","Vol.","% var."
    "05.10.2026","547,60","535,00","552,50","532,60","18,32K","3,03%"

Mismas reglas de integridad que el resto del repo (ver CLAUDE.md):
  * Parseo defensivo: un encabezado distinto, una fecha o un número ilegible hacen fallar
    el archivo completo en voz alta (nunca se convierte nada en 0 ni se adivina).
  * Cross-check: la columna "% var." de Investing se compara contra la variación calculada
    con los cierres del propio archivo. Si no calza (fila perdida, número mal leído), se
    avisa y ese archivo NO se fusiona.
  * low <= close <= high: se ensancha high/low con el propio close; close nunca se toca.
  * Fusión por fecha: lo último subido gana para esa fecha; nunca se reemplaza la serie.

Uso:  python scripts/importar_investing_csv.py            (todas las variables de VARIABLES)
"""
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
HISTORIA_DIR = ROOT / "data" / "historia"
MANUAL_DIR = ROOT / "data" / "manual"
TRIM_DAYS = 1900  # igual que fetch_and_update.py: ~5,2 años
TOLERANCIA_VAR = 0.02  # puntos porcentuales: Investing redondea "% var." a 2 decimales

VARIABLES = [
    {
        "id": "azucar_londres", "nombre": "Azúcar Blanca Nº5 Londres", "ticker": "Investing: London Sugar No.5",
        "unidad": "USD/ton métrica", "dec": 2,
        "exchange": "ICE Futures Europe", "contrato": "White Sugar No.5, contrato continuo (mes activo)",
        "fuente": "Investing.com, Datos históricos (CSV descargado a mano)",
        "fuente_url": "https://es.investing.com/commodities/london-sugar-historical-data",
        "rango": (100, 2000),  # plausibilidad en USD/t: solo atrapa lecturas absurdas
    },
]

COLUMNAS = {  # nombre en el CSV -> campo
    "Fecha": "fecha", "Date": "fecha",
    "Último": "close", "Price": "close",
    "Máximo": "high", "High": "high",
    "Mínimo": "low", "Low": "low",
    "% var.": "var", "Change %": "var",
}


class FormatoInesperado(Exception):
    pass


def _numero(texto, decimal_coma):
    t = texto.strip().replace("%", "")
    if decimal_coma:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        raise FormatoInesperado(f"número ilegible: {texto!r}")
    return float(t)


def _fecha(texto):
    t = texto.strip()
    for fmt in ("%d.%m.%Y", "%m/%d/%Y"):  # español / inglés
        try:
            return dt.datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise FormatoInesperado(f"fecha ilegible: {texto!r}")


def leer_csv(path, var):
    with open(path, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f))
    if not filas:
        raise FormatoInesperado("archivo vacío")
    encabezado = [c.strip() for c in filas[0]]
    idx = {COLUMNAS[c]: i for i, c in enumerate(encabezado) if c in COLUMNAS}
    if set(idx) != {"fecha", "close", "high", "low", "var"}:
        raise FormatoInesperado(f"encabezado inesperado: {encabezado}")
    decimal_coma = encabezado[idx["fecha"]] == "Fecha"

    puntos = {}
    for n, fila in enumerate(filas[1:], start=2):
        if not any(c.strip() for c in fila):
            continue
        try:
            fecha = _fecha(fila[idx["fecha"]])
            close, high, low = (_numero(fila[idx[k]], decimal_coma) for k in ("close", "high", "low"))
            variacion = _numero(fila[idx["var"]], decimal_coma)
        except (FormatoInesperado, IndexError) as e:
            raise FormatoInesperado(f"fila {n}: {e}")
        if fecha.isoformat() in puntos:
            raise FormatoInesperado(f"fila {n}: fecha repetida {fecha}")
        lo, hi = var["rango"]
        if not all(lo <= v <= hi for v in (close, high, low)):
            raise FormatoInesperado(f"fila {n}: valor fuera de rango plausible {lo}-{hi}: {fila}")
        puntos[fecha.isoformat()] = {"fecha": fecha.isoformat(), "close": round(close, var["dec"]),
                                     "high": round(max(high, close), var["dec"]),
                                     "low": round(min(low, close), var["dec"]), "_var": variacion}
    if not puntos:
        raise FormatoInesperado("el archivo no trae filas de datos")

    # Cross-check con la columna "% var." de Investing (dato independiente del cierre).
    serie = sorted(puntos.values(), key=lambda p: p["fecha"])
    malos = []
    for ant, p in zip(serie, serie[1:]):
        calculada = (p["close"] / ant["close"] - 1) * 100
        if abs(calculada - p["_var"]) > TOLERANCIA_VAR:
            malos.append(f"{p['fecha']}: % var. de Investing {p['_var']:+.2f}% vs calculada {calculada:+.2f}%")
    if malos:
        raise FormatoInesperado("la columna '% var.' no calza con los cierres (¿falta una fila?): "
                                + "; ".join(malos[:5]) + (f" (y {len(malos) - 5} más)" if len(malos) > 5 else ""))
    for p in serie:
        del p["_var"]
    return serie


def merge_and_trim(existente, nuevos):
    by_fecha = {p["fecha"]: p for p in existente}
    for p in nuevos:
        by_fecha[p["fecha"]] = p
    serie = sorted(by_fecha.values(), key=lambda p: p["fecha"])
    corte = (dt.date.today() - dt.timedelta(days=TRIM_DAYS)).isoformat()
    return [p for p in serie if p["fecha"] >= corte]


def importar(var, advertencias):
    carpeta = MANUAL_DIR / var["id"]
    archivos = sorted(carpeta.glob("*.csv")) if carpeta.exists() else []
    if not archivos:
        advertencias.append(f"{var['id']}: no hay CSV en {carpeta.relative_to(ROOT)}")
        return False
    doc_path = HISTORIA_DIR / f"{var['id']}.json"
    doc = json.load(open(doc_path, encoding="utf-8")) if doc_path.exists() else {"serie": []}
    serie = doc.get("serie", [])
    leidos = []
    for path in archivos:
        try:
            leidos.append((path, leer_csv(path, var)))
        except FormatoInesperado as e:
            advertencias.append(f"{path.relative_to(ROOT)}: {e} — NO se fusionó, revisar el archivo")
    # Si dos archivos traen la misma fecha, gana la descarga más reciente: se fusionan en
    # orden de la última fecha que contiene cada archivo (el nombre del archivo no importa).
    for path, puntos in sorted(leidos, key=lambda x: (x[1][-1]["fecha"], x[0].name)):
        serie = merge_and_trim(serie, puntos)
        print(f"  {path.name}: {len(puntos)} días ({puntos[0]['fecha']} a {puntos[-1]['fecha']})")
    if not leidos:
        return False
    meta = {k: v for k, v in var.items() if k != "rango"}
    if serie != doc.get("serie") or any(doc.get(k) != v for k, v in meta.items()):
        doc.update(meta)
        doc["serie"] = serie
        doc["ultima_actualizacion"] = dt.datetime.now(ZoneInfo("America/Santiago")).isoformat(timespec="seconds")
        with open(doc_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        u = serie[-1]
        print(f"{var['nombre']}: n={len(serie)} desde {serie[0]['fecha']} último={u['fecha']} close={u['close']}")
    else:
        print(f"{var['nombre']}: sin cambios")
    return True


def main():
    advertencias = []
    ok = [importar(v, advertencias) for v in VARIABLES]
    if advertencias:
        print("\nAdvertencias de esta corrida:")
        for a in advertencias:
            print(" -", a)
    # Falla en voz alta (job en rojo) si algún archivo no se pudo leer.
    if advertencias or not all(ok):
        sys.exit("ERROR: hubo archivos que no se fusionaron; ver advertencias arriba.")


if __name__ == "__main__":
    main()
