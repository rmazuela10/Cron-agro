"""
fetch_and_update.py — corre dentro de GitHub Actions (con cron). Hace fetch directo
al endpoint `chart` de Yahoo Finance (sin navegador: el runner de GitHub tiene salida
a internet normal, a diferencia del sandbox de Claude donde este pipeline nació), lo
parsea a la defensiva, cruza el último dato contra meta.regularMarketPrice para
descartar anomalías, y lo fusiona por fecha sobre data/historia/<id>.json — nunca
reemplaza la serie completa, solo agrega/actualiza por fecha y recorta el extremo
viejo más allá de ~5 años.

Mismas reglas de integridad que el resto del proyecto (ver PROCESO_ACTUALIZACION_DASHBOARD.md
en el proyecto de Claude): nunca convertir un hueco en 0, nunca inventar un dato,
nunca aceptar un valor que no pasó el cross-check.
"""
import json
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent.parent
HISTORIA_DIR = ROOT / "data" / "historia"
TRIM_DAYS = 1900  # ~5.2 años — se recorta cualquier punto más viejo que esto tras fusionar
CROSS_CHECK_TOLERANCE = 0.01  # 1% — tolerancia entre el último bar y meta.regularMarketPrice

TICKERS = [
    {"id": "maiz_us", "nombre": "Maíz", "ticker": "ZC=F", "unidad": "USd/bushel", "dec": 2},
    {"id": "trigo_us", "nombre": "Trigo", "ticker": "ZW=F", "unidad": "USd/bushel", "dec": 2},
    {"id": "soya_us", "nombre": "Soya", "ticker": "ZS=F", "unidad": "USd/bushel", "dec": 2},
    {"id": "avena_us", "nombre": "Avena", "ticker": "ZO=F", "unidad": "USd/bushel", "dec": 2},
    {"id": "harina_soya_us", "nombre": "Harina de Soya", "ticker": "ZM=F", "unidad": "USD/ton corto", "dec": 1},
    {"id": "aceite_soya_us", "nombre": "Aceite de Soya", "ticker": "ZL=F", "unidad": "USd/lb", "dec": 2},
    {"id": "azucar_mundial", "nombre": "Azúcar", "ticker": "SB=F", "unidad": "USd/lb", "dec": 2},
    {"id": "petroleo_brent", "nombre": "Petróleo Brent", "ticker": "BZ=F", "unidad": "USD/barril", "dec": 2},
]

ENDPOINT_TPL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=3mo&interval=1d"
# Yahoo rechaza peticiones sin un User-Agent de navegador real.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_chart(ticker):
    url = ENDPOINT_TPL.format(ticker=ticker)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def parse_fresh(g, payload):
    """Parsea la respuesta cruda a una lista de puntos {fecha,close,high,low}, a la
    defensiva (huecos se omiten, nunca se convierten en 0), y hace el cross-check
    anti-anomalía sobre el último bar. Devuelve (puntos, advertencia_o_None)."""
    result = payload.get("chart", {}).get("result")
    if not result:
        return [], f"{g['ticker']}: respuesta sin 'result'"
    r = result[0]
    meta = r.get("meta", {})
    tz_name = meta.get("exchangeTimezoneName") or "America/New_York"
    tz = ZoneInfo(tz_name)

    timestamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []

    n = len(timestamps)
    if not (len(closes) == len(highs) == len(lows) == n):
        return [], f"{g['ticker']}: largos de arreglo inconsistentes"

    puntos = []
    for i in range(n):
        c, h, l = closes[i], highs[i], lows[i]
        if c is None or h is None or l is None:
            continue  # hueco real — se omite, nunca se convierte en 0
        fecha = dt.datetime.fromtimestamp(timestamps[i], tz=tz).date().isoformat()
        puntos.append({
            "fecha": fecha,
            "close": round(float(c), g["dec"]),
            "high": round(float(h), g["dec"]),
            "low": round(float(l), g["dec"]),
        })

    if not puntos:
        return [], f"{g['ticker']}: 0 observaciones válidas tras el parseo"

    # Cross-check anti-anomalía: el close del último bar vs. el precio de mercado
    # reportado independientemente en la misma respuesta. Si difieren demasiado,
    # se descarta SOLO ese último bar (el resto de la ventana de 3 meses se conserva).
    regular_price = meta.get("regularMarketPrice")
    if regular_price is not None and puntos:
        last = puntos[-1]
        diff = abs(last["close"] - regular_price) / regular_price
        if diff > CROSS_CHECK_TOLERANCE:
            advertencia = (
                f"{g['ticker']}: último bar ({last['close']}) difiere "
                f"{diff*100:.1f}% de regularMarketPrice ({regular_price}) — se descarta ese bar"
            )
            puntos = puntos[:-1]
            return puntos, advertencia

    return puntos, None


def merge_and_trim(existing_serie, nuevos_puntos):
    by_fecha = {p["fecha"]: p for p in existing_serie}
    for p in nuevos_puntos:
        by_fecha[p["fecha"]] = p
    serie = sorted(by_fecha.values(), key=lambda p: p["fecha"])
    corte = (dt.date.today() - dt.timedelta(days=TRIM_DAYS)).isoformat()
    return [p for p in serie if p["fecha"] >= corte]


def main():
    HISTORIA_DIR.mkdir(parents=True, exist_ok=True)
    ahora = dt.datetime.now(ZoneInfo("America/Santiago")).isoformat(timespec="seconds")
    advertencias = []

    for g in TICKERS:
        doc_path = HISTORIA_DIR / f"{g['id']}.json"
        if doc_path.exists():
            with open(doc_path, encoding="utf-8") as f:
                doc = json.load(f)
        else:
            doc = {
                "id": g["id"], "nombre": g["nombre"], "ticker": g["ticker"],
                "unidad": g["unidad"], "dec": g["dec"], "serie": [],
            }

        try:
            payload = fetch_chart(g["ticker"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            advertencias.append(f"{g['ticker']}: fetch falló ({e}) — se mantiene el dato anterior")
            continue

        nuevos_puntos, advertencia = parse_fresh(g, payload)
        if advertencia:
            advertencias.append(advertencia)
        if not nuevos_puntos:
            continue  # nada válido que fusionar esta vez — se mantiene el dato anterior tal cual

        doc["serie"] = merge_and_trim(doc.get("serie", []), nuevos_puntos)
        doc["ultima_actualizacion"] = ahora
        # metadata que no cambia entre corridas, por si el doc se creó vacío recién:
        doc.setdefault("exchange", None)
        doc.setdefault("contrato", None)

        with open(doc_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        ultimo = doc["serie"][-1]
        print(f"  {g['nombre']:16s} n={len(doc['serie']):4d} último={ultimo['fecha']} close={ultimo['close']}")

    # Índice liviano — útil para que el dashboard sepa qué hay sin tener que pedir los 8 archivos.
    index = {"ultima_corrida": ahora, "commodities": [g["id"] for g in TICKERS]}
    with open(HISTORIA_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    if advertencias:
        print("\nAdvertencias de esta corrida:")
        for a in advertencias:
            print(" -", a)


if __name__ == "__main__":
    main()
