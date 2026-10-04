"""historico_ddgs.py — construye el histórico semanal de DDGS FOB Vessel Gulf (New Orleans)
en data/historia/ddgs_fob_gulf.json, a partir de los archivos públicos de USDA AMS.

Mismo formato JSON que las demás variables del repo, pero cada punto lleva solo
{fecha, close} (sin high ni low). close = promedio semanal que publica USDA.

De dónde salen los datos:
  1. ESMIS (biblioteca NAL de USDA): copia de cada AMS_3616 desde el primero
     (22-jul-2022) hasta sep-2025, donde dejó de actualizarse.
  2. MyMarketNews (USDA AMS): archivo completo de AMS_3616 hasta la semana pasada.
  3. El reporte vigente: https://www.ams.usda.gov/mnreports/ams_3616.pdf

Ambos archivos repiten muchos de los mismos PDFs; la fusión por fecha deja un solo punto
por semana (si hay dos publicaciones de la misma semana, gana la más reciente). Si uno de
los archivos no responde, se usa el otro y se avisa.

La serie empieza el 2022-07-22 porque ahí empieza el reporte. Antes de eso USDA no
publicaba un precio FOB Vessel para el Golfo (el reporte diario antiguo traía "CIF NOLA",
que es otra base de precio), así que no se rellena hacia atrás.

Se puede correr de nuevo cuando se quiera: no borra nada, solo agrega o actualiza semanas.
Uso:  python scripts/historico_ddgs.py   (requiere pdftotext, del paquete poppler-utils)
"""
import datetime as dt
import re
import sys
import urllib.error

from fetch_ddgs import (URL_VIGENTE, actualizar, cargar_doc, links_esmis,
                        links_mymarketnews, terminar)


def fecha_semana_mmn(url):
    """MyMarketNews guarda cada PDF en una carpeta con el lunes de la semana del reporte
    (.../3616/2026-09-28/...). Devuelve el viernes de esa semana, o None si no calza."""
    m = re.search(r"/3616/(\d{4}-\d{2}-\d{2})/", url)
    return (dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=4)).isoformat() if m else None


def main():
    advertencias, leidos = [], 0

    # 1) ESMIS primero: responde rápido y cubre jul-2022 a sep-2025.
    try:
        urls = links_esmis()
        print(f"ESMIS: {len(urls)} reportes AMS_3616")
        leidos += actualizar(urls, advertencias, verbose=True)
    except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
        advertencias.append(f"No se pudo listar el archivo ESMIS: {e}")

    # 2) MyMarketNews: es lento, así que solo se bajan las semanas que aún faltan.
    #    Son los mismos PDFs de USDA, así que no se pierde nada.
    try:
        urls = links_mymarketnews()
        ya = {p["fecha"] for p in cargar_doc().get("serie", [])}
        faltan = [u for u in urls if fecha_semana_mmn(u) not in ya]
        print(f"MyMarketNews: {len(urls)} reportes AMS_3616, {len(faltan)} semanas por bajar")
        leidos += actualizar(faltan, advertencias, verbose=True)
    except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
        advertencias.append(f"No se pudo listar el archivo MyMarketNews: {e}")

    # 3) El vigente al final: es la publicación más reciente, así gana en su semana.
    leidos += actualizar([URL_VIGENTE], advertencias, verbose=True)
    terminar(advertencias, leidos)
    # Lo que sí se leyó ya quedó guardado. Si un archivo no respondió, el job termina en
    # rojo para que se note que faltan semanas; basta con volver a correrlo más tarde.
    if any(a.startswith("No se pudo listar") for a in advertencias):
        sys.exit("ATENCIÓN: un archivo de USDA no respondió; pueden faltar semanas. Reintentar más tarde.")


if __name__ == "__main__":
    main()
