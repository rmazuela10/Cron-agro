# Dashboard Commodities Agrícolas y Energía — infraestructura de datos en vivo

Este repositorio es el backend real que le falta al `dashboard_granos.html` para
tener un botón "Actualizar" que funcione fuera de Claude: un cron de GitHub Actions
que hace fetch a Yahoo Finance de forma automática, y GitHub Pages sirviendo el
resultado como archivos JSON públicos a los que cualquier navegador puede hacer
`fetch()` sin problema de CORS.

## Qué hay acá

```
.github/workflows/actualizar-precios.yml   ← el cron: define cuándo corre
scripts/fetch_and_update.py                 ← fetch + parseo defensivo + cross-check + fusión
data/historia/*.json                        ← un archivo por commodity (8), con ~5 años de histórico
```

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

Están sembrados con el histórico de 5 años que ya teníamos (capturado 2026-10-01).
A partir de que el workflow corra por primera vez, cada ejecución va a fusionar los
días nuevos sobre esto — nunca reemplaza la serie completa, solo agrega/actualiza
por fecha y recorta el extremo más viejo que ~5.2 años para que no crezca sin límite.

## Puesta en marcha (una vez)

1. **Crea el repositorio en GitHub** (puede ser privado o público — para que GitHub
   Pages sirva los JSON públicamente sin login, necesita ser público, o privado con
   GitHub Pro/Team/Enterprise).
2. **Sube estos archivos** tal cual están, respetando la estructura de carpetas.
3. **Habilita permisos de escritura para Actions:** en el repo, ve a
   `Settings → Actions → General → Workflow permissions` y marca
   **"Read and write permissions"**. Sin esto, el paso de `git push` del workflow
   va a fallar con un error de permisos — es el error más común al configurar esto.
4. **Habilita GitHub Pages:** `Settings → Pages → Build and deployment → Source:
   Deploy from a branch`, rama `main` (o la que uses), carpeta `/ (root)`. Esto le da
   a `data/historia/maiz_us.json` una URL pública fija, del tipo:
   `https://<tu-usuario>.github.io/<nombre-del-repo>/data/historia/maiz_us.json`
5. **Pruébalo a mano antes de confiar en el cron:** en la pestaña **Actions** del
   repo, entra al workflow "Actualizar precios de commodities" y usa el botón
   "Run workflow" (existe gracias a `workflow_dispatch` en el `.yml`). Revisa el log
   — debería terminar con un commit nuevo en `data/historia/` (o decir "sin cambios"
   si no hay sesión de mercado nueva).

Desde ahí, el cron corre solo: lunes a viernes, a las 8:00/12:00/16:00/20:00 hora de
Chile (ver la nota dentro del `.yml` sobre el ajuste de horario de invierno — GitHub
Actions no ajusta DST automáticamente, hay que editar el archivo a mano en abril).

## Qué NO incluye todavía este repositorio

El `dashboard_granos.html` que ya tienes **no está conectado a esto todavía** — sigue
leyendo la base estática embebida (y, dentro del Artifact de Claude, la colección
`historia` de ahí, que es un sistema aparte). Conectar el botón "Actualizar" del
`.html` a estos JSON (haciendo `fetch()` a la URL de GitHub Pages en vez de depender
de `window.claude`) es un cambio de código deliberado, pendiente, para cuando quieras
dar ese paso — no se tocó en esta entrega para no mezclar "preparar la infraestructura"
con "cambiar el dashboard que ya funciona".

## Consideración de licencia (ya discutida antes, vale repetirla acá)

Los datos vienen de Yahoo Finance (futuros CBOT/ICE), documentados hasta ahora como
"uso interno, no redistribuir" porque la captura era manual y puntual. Automatizar
esto en un repositorio público, con un cron corriendo solo varias veces al día y
sirviendo los datos a cualquiera que tenga la URL, se parece bastante más a
"redistribución en vivo" que a una captura puntual para uso propio. Si el repo va a
ser público, vale la pena revisar esto — por ejemplo, dejando el repo **privado**
(con un plan de GitHub que permita Pages privado) en vez de público, o evaluando las
fuentes 100% libres documentadas en `free-data-sources.md` (USDA AMS para
granos/oleaginosas, EIA para energía) como reemplazo de Yahoo si el uso va a ser más
amplio que el tuyo propio.
