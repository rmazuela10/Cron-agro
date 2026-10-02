# Precios de Commodities Agrícolas y Energía — pipeline automático con GitHub Actions

Pipeline que descarga precios de futuros agrícolas y energéticos desde Yahoo Finance
de forma automática varias veces al día, y publica el resultado como archivos JSON
estáticos vía GitHub Pages — consumibles con `fetch()` desde cualquier navegador, sin
restricciones de CORS ni autenticación.

## Qué hace

- `.github/workflows/actualizar-precios.yml` ejecuta el pipeline con un cron de
  GitHub Actions: lunes a viernes a las 11, 15, 19 y 23 UTC (8:00 / 12:00 / 16:00 /
  20:00 hora de Chile en horario de verano — ver la nota dentro del archivo sobre el
  ajuste necesario cuando Chile pasa a horario de invierno, ya que GitHub Actions no
  ajusta DST automáticamente). También puede dispararse manualmente desde la pestaña
  **Actions** (`workflow_dispatch`).
- En cada corrida, `scripts/fetch_and_update.py` hace una petición HTTP directa al
  endpoint `chart` de Yahoo Finance para cada uno de los 8 tickers configurados
  (maíz, trigo, soya, avena, harina de soya, aceite de soya, azúcar y petróleo
  Brent). Parsea la respuesta a la defensiva — un dato faltante nunca se convierte en
  `0` — y cruza el último valor de la serie contra `meta.regularMarketPrice` de la
  misma respuesta para descartar anomalías (tolerancia 1%).
- El resultado se fusiona por fecha sobre `data/historia/<id>.json`: nunca reemplaza
  la serie completa, solo agrega o actualiza por fecha y recorta el extremo más
  antiguo de la ventana (~5,2 años) para que el archivo no crezca sin límite.
- Si hubo cambios, el workflow hace commit y push automático de los JSON
  actualizados con el token por defecto de GitHub Actions (autor
  `github-actions[bot]`). Si no hay sesión de mercado nueva que publicar (fin de
  semana, feriado), no se genera ningún commit.
- GitHub Pages sirve el contenido del repositorio tal cual, así que cada archivo
  queda disponible en una URL pública fija, del tipo:
  `https://<usuario>.github.io/<repo>/data/historia/<id>.json`

## Estructura

```
.github/workflows/actualizar-precios.yml   ← el cron: define cuándo corre
scripts/fetch_and_update.py                 ← fetch + parseo defensivo + cross-check + fusión
data/historia/*.json                        ← un archivo por commodity (8), con ~5 años de histórico
```

## Formato de los datos

Cada commodity es un archivo JSON independiente con esta forma:

```json
{
  "id": "maiz_us",
  "nombre": "Maíz",
  "ticker": "ZC=F",
  "unidad": "USd/bushel",
  "dec": 2,
  "ultima_actualizacion": "2026-10-01T12:08:02-03:00",
  "serie": [
    {"fecha": "2026-09-30", "close": 500.75, "high": 526.25, "low": 498.75},
    {"fecha": "2026-10-01", "close": 497.75, "high": 505.00, "low": 497.75}
  ]
}
```

Cada archivo arranca con un histórico base de ~5 años. Desde la primera corrida del
workflow, cada ejecución fusiona los días nuevos sobre esa base, sin reemplazarla.

## Alcance actual

Este repositorio solo obtiene y publica los datos — no incluye ningún frontend.
Consumir estos JSON desde una interfaz (por ejemplo, un `fetch()` a las URLs de
GitHub Pages) es responsabilidad de quien los use y no es parte de este pipeline.

## Fuente de datos y licencia

Los datos provienen del endpoint no oficial `chart` de Yahoo Finance (futuros
CBOT/ICE/NYMEX), que no ofrece una licencia explícita para redistribución
automatizada y pública. Publicar estos datos en un repositorio público,
actualizados varias veces al día y servidos a cualquiera que tenga la URL,
constituye una forma de redistribución en vivo, no solo una captura puntual para
uso propio. Quien despliegue este pipeline debería evaluar alguna de estas dos
alternativas si el uso va a ir más allá de lo personal: mantener el repositorio
**privado** (requiere un plan de GitHub que permita Pages privado), o sustituir
Yahoo Finance por fuentes públicas sin restricciones de licencia — por ejemplo
USDA AMS para precios físicos de granos y oleaginosas, o EIA para energía.
