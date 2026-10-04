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
* Cada punto es `{fecha, close, high, low}` (excepción: `ddgs_fob_gulf` guarda solo `{fecha, close}`). Para series con rango (p. ej. precios AMS min–max): `close` = promedio, `high` = máximo, `low` = mínimo.

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

## DDGS FOB Vessel Gulf (fuente: reporte semanal de USGC)

Variable semanal en `data/historia/ddgs_fob_gulf.json`, con script y workflow SEPARADOS del de Yahoo (`scripts/fetch_ddgs.py` + `scripts/ocr_tabla.py` + `.github/workflows/actualizar-ddgs.yml`, cron diario 13:00 UTC). No tocar `fetch_and_update.py` ni su workflow.

* Fuente (decisión de Ramon, 2026-10-04): `https://grains.org/ddgs_report/` (U.S. Grains & BioProducts Council). Cada post semanal enlaza un PDF; en la pág. 2 está la "DDGS Price Table" (USD/ton métrica, de World Perspectives) con la fila "FOB Vessel GULF" y tres columnas de meses. Se guarda la PRIMERA columna (mes más cercano) como `close`; `fecha` = fecha del título del post.
* La tabla es una IMAGEN (sin capa de texto) y su diseño cambió (grilla naranja 2021-23, filas oscuras 2024, sin grilla desde 2025). Se lee con OCR (tesseract) de muchas formas independientes y se exige consenso (≥3 lecturas idénticas y ≥75% de las válidas), rango 100-700 y los 3 meses a ≤20% entre sí. Si no hay consenso, la semana se descarta y se avisa (nunca se adivina).
* Histórico: solo desde enero de 2021 (Ramon pidió no ir más atrás). `scripts/historico_ddgs.py` recorre el listado (solo agrega semanas faltantes; `--rehacer` relee todo). Desde Actions: "Run workflow" con `historico` = true.
* Esta serie guarda solo `{fecha, close}`, sin `high` ni `low` (decisión de Ramon, 2026-10-04). No copiar el texto de análisis de USGC (copyright): solo el número.
* El proxy del entorno de Claude bloquea grains.org: para probar contra la fuente hay que correr en GitHub Actions.
* Alternativa descartada: USDA AMS National Weekly Ethanol Report (`ams_3616.pdf`, fila New Orleans FOB OV, USD/short ton). Sirve como cross-check manual si alguna vez hace falta.

## Fuera de este repo

El dashboard (`dashboard_granos.html`, hecho en React/Recharts y compilado a un solo HTML) y sus pruebas viven en el proyecto "Dashboard interactivo agro" de Claude (Cowork). Para que DDGS aparezca como pestaña, allá hay que agregar una variable con `id: "ddgs_fob_gulf"` y apuntar al JSON de este repo. No intentes reconstruir el dashboard desde este repo.
