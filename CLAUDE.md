# CLAUDE.md — Cron-agro (pipeline de precios para el dashboard de commodities)

Idioma de trabajo: español. El usuario es Ramon (rmazuela@fen.uchile.cl, GitHub: rmazuela10). Explica en simple, sin jerga innecesaria. Antes de hacer push a `main`, muestra el `git diff` resumido y pide confirmación (salvo que el usuario diga explícitamente "súbelo").

## Qué es este repo

Backend de datos de un dashboard interactivo de commodities y tipo de cambio. Un workflow de GitHub Actions corre un script de Python que baja precios desde Yahoo Finance, los valida, los fusiona por fecha sobre un histórico de ~5 años y hace commit automático. GitHub Pages sirve los JSON públicamente (CORS abierto), y el dashboard (un HTML aparte, que NO vive en este repo) hace `fetch()` a ellos cuando se presiona "Actualizar".

```
.github/workflows/actualizar-precios.yml   cron: */15 * * * 1-5 (cada 15 min, lun-vie, UTC), con bloque concurrency
scripts/fetch_and_update.py                fetch Yahoo + parseo defensivo + cross-check + sanitize_high_low + merge_and_trim
data/historia/<id>.json                    una variable por archivo (12 hoy) + index.json
```

URL pública: `https://rmazuela10.github.io/Cron-agro/data/historia/<id>.json`

Variables actuales (id → ticker Yahoo): maiz_us ZC=F, trigo_us ZW=F, soya_us ZS=F, avena_us ZO=F, harina_soya_us ZM=F, aceite_soya_us ZL=F, azucar_mundial SB=F, petroleo_brent BZ=F, usdclp CLP=X, usdbrl BRL=X, usdpen PEN=X, dxy DX-Y.NYB.

## Formato JSON (contrato con el dashboard — NO cambiar sin avisar)

```json
{
  "id": "maiz_us", "nombre": "Maíz", "ticker": "ZC=F", "unidad": "USd/bushel", "dec": 2,
  "serie": [{"fecha": "2026-10-01", "close": 497.75, "high": 505.0, "low": 497.75}],
  "ultima_actualizacion": "2026-10-01T12:08:02-03:00",
  "exchange": "CBOT", "contrato": "Corn Futures,Dec-2026"
}
```

* `id` es EXACTAMENTE el nombre del archivo y lo que usa el dashboard para armar la URL.
* La serie va ordenada por `fecha` ascendente, sin fechas duplicadas, recortada a ~1900 días (`TRIM_DAYS`).
* Cada punto es `{fecha, close, high, low}`. Para series con rango (p. ej. precios AMS min–max): `close` = promedio, `high` = máximo, `low` = mínimo.

## Reglas de integridad de datos (no negociables)

1. Nunca inventar ni rellenar. Un dato faltante queda faltante. Nunca convertir "sin dato" en 0, nunca interpolar, nunca arrastrar el valor anterior en silencio.
2. Parseo defensivo: los parsers devuelven `None`/excepción ante lo inesperado, jamás 0.
3. Cross-check: el último valor se compara contra una segunda ruta independiente cuando exista (en Yahoo: `meta.regularMarketPrice`, tolerancia 1%); si falla, se descarta ese punto y se avisa.
4. Invariante `low <= close <= high`: `sanitize_high_low()` ensancha high/low con el propio close; NUNCA se modifica `close`.
5. Fusión por fecha (`merge_and_trim`): el último valor gana por fecha; nunca se reemplaza la serie completa.
6. Aislamiento de fallos: si una fuente/ticker falla, se mantiene el dato anterior y el resto sigue. Un cambio de formato en una fuente nueva no debe poder romper el pipeline de Yahoo.
7. Si no se puede leer un dato con certeza, se reporta al usuario en vez de aproximarlo.

## Limitaciones conocidas

* GitHub Actions no soporta cron más frecuente que cada 5 min (y no es exacto bajo carga). Se eligió 15 min.
* Yahoo `interval=1d` entrega velas diarias: la mayoría de las corridas terminan en "sin cambios" (esperado).
* Yahoo a veces entrega `close` fuera de `[low, high]` (muy frecuente en PEN=X): ya cubierto por sanitize_high_low.
* Cambio de horario de Chile: el cron actual no fija horas, así que no requiere ajuste.

## TAREA PENDIENTE: agregar DDGS (derivado del maíz) con histórico desde 2017

Objetivo: nueva variable semanal "DDGS FOB Vessel Gulf" (USD/ton) en `data/historia/ddgs_fob_gulf.json` (mismo formato; `freq` semanal, un punto por semana), con un script y workflow SEPARADOS del de Yahoo (`scripts/fetch_ddgs.py` + `.github/workflows/actualizar-ddgs.yml`, cron diario basta: la fuente es semanal). No tocar `fetch_and_update.py` ni su workflow.

El usuario pidió construir el histórico desde 2017 y la actualización semanal desde: `https://grains.org/ltamex/resources-page/reports/ddgs_report/` (US Grains & BioProducts Council).

### Hallazgos de la investigación previa (hecha desde un sandbox sin acceso directo a esos sitios; VERIFÍCALOS tú)

* Ese listado es estable (45 páginas, el más nuevo primero). Cada entrada enlaza a un post `https://grains.org/?p=NNNNN` (ID de WordPress sin patrón) que a su vez enlaza a un PDF con nombre tipo `https://grains.org/wp-content/uploads/2026/10/Weekly-DDGS-Market-Report-10.1.26.pdf` (el patrón del nombre cambió con los años: `DDGS-12.9.21.pdf`, `04-20-2023.pdf`, etc.).
* PDF de oct-2026: el precio absoluto de DDGS aparece solo en gráficos que parecían imágenes sin capa de texto. Como texto solo vienen los spreads ("FOB U.S. Gulf DDGS to SMB spread: $151", "to corn spread: $63.66") y estadísticas de exportación. En un PDF de dic-2021 los gráficos sí tenían etiquetas de texto ("$272.00"). Es decir, el formato cambió con los años. Esta conclusión salió de un extractor de texto con IA (lossy): confírmala descargando los PDFs y usando pdfplumber/pdftotext (y revisando si hay imágenes embebidas) en una muestra de años (2017, 2019, 2021, 2023, 2024, 2026).
* Algunos posts antiguos (p. ej. `?p=59210`, sep-2024) traen el precio como texto en el HTML: "USDA reported DDGS prices averaged $140 per short ton in the September 20 National Weekly Ethanol Report".
* El precio que citan viene de USDA AMS National Weekly Ethanol Report, que tiene URL fija sobrescrita cada semana: `https://www.ams.usda.gov/mnreports/ams_3616.pdf` (verificado el 2-oct-2026: "Report for 9/28/2026 - 10/2/2026 – Final"). En la tabla "Distillers Grain Dried 10%", subsección "Export Point", la fila `New Orleans Ask 245.00-260.00 DN 5.00 254.50 191.67 FOB - OV Current` es el FOB Vessel Gulf (columnas: precio min-max, cambio, promedio, año atrás, flete, entrega; `OV` = Ocean Vessel). Texto plano extraíble. (`sj_gr113.txt` es un reporte legado congelado desde 2022: NO usarlo.)
* La API MARS de USDA AMS (`marsapi.ams.usda.gov`) requiere key gratuita (eAuth, basic-auth); da JSON y archivo histórico.

### Decisión pendiente del usuario (pregúntale antes de construir)

¿Fuente numérica = USDA AMS (primaria, texto extraíble; el link de USGC queda solo como referencia) o USGC (spread + maíz de Yahoo, que sería un número DERIVADO y habría que etiquetarlo así)? Mi recomendación: USDA para el dato, y evaluar MARS API / archivo histórico de USDA para el histórico desde 2017. Solo precio, sin copiar el texto de análisis de USGC (tiene copyright; el número es un hecho, el texto no). Granularidad elegida: solo FOB Vessel Gulf (New Orleans).

Cómo mapear a la serie: `close` = promedio, `high` = máximo del rango, `low` = mínimo; `fecha` = fin de semana del reporte. Marcar en metadata cadencia "Semanal". Conservar rango y promedio (nunca solo el punto medio).

### Verificación obligatoria antes de dar algo por terminado

* Descargar y parsear a mano 3-4 reportes de épocas distintas y comparar contra lo que se ve en el PDF.
* Que el parser falle en voz alta (excepción/advertencia) si cambia el formato, nunca que devuelva 0 o un valor inventado.
* Probar `python scripts/fetch_ddgs.py` en local, y luego "Run workflow" manual en la pestaña Actions antes de confiar en el cron.
* Rutas: el YAML va en `.github/workflows/` (con el punto). Ojo: pushear archivos de workflows exige el permiso `workflow` en el token (`gh auth login` lo pide).

## Fuera de este repo

El dashboard (`dashboard_granos.html`, hecho en React/Recharts y compilado a un solo HTML) y sus pruebas viven en el proyecto "Dashboard interactivo agro" de Claude (Cowork). Para que DDGS aparezca como pestaña, allá hay que agregar una variable con `id: "ddgs_fob_gulf"` y apuntar al JSON de este repo. No intentes reconstruir el dashboard desde este repo.
