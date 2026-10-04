"""Sonda temporal (se borra antes de fusionar): explora fuentes USDA desde el runner."""
import re, subprocess, urllib.request, json
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get(url, binary=False):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40)
        b = r.read()
        print(f"[{r.status}] {url} ({len(b)} bytes, {r.headers.get('Content-Type')})")
        return b if binary else b.decode("utf-8", "replace")
    except Exception as e:
        print(f"[ERR] {url}: {e}")
        return None

def pdftext(b, name):
    open(f"/tmp/{name}.pdf", "wb").write(b)
    subprocess.run(["pdftotext", "-layout", f"/tmp/{name}.pdf", f"/tmp/{name}.txt"], check=True)
    return open(f"/tmp/{name}.txt").read()

def ddgs_section(t):
    i = t.find("Distillers Grain Dried")
    return t[i:i+2500] if i >= 0 else "(NO ENCONTRADO 'Distillers Grain Dried')"

print("===== 1. ams_3616.pdf actual =====")
b = get("https://www.ams.usda.gov/mnreports/ams_3616.pdf", True)
if b:
    t = pdftext(b, "actual"); print(t[:600]); print(ddgs_section(t))

print("===== 2. ESMIS listado national-weekly-ethanol-report =====")
for p in [0, 16, 30, 60]:
    h = get(f"https://esmis.nal.usda.gov/publication/national-weekly-ethanol-report?page={p}")
    if h:
        links = re.findall(r'href="([^"]+release-files[^"]+)"', h)
        dates = re.findall(r'(\w{3,9} \d{1,2}, \d{4})', h)
        print("  links:", len(links), links[:2], links[-2:]); print("  fechas:", dates[:3], dates[-3:])
        last = re.findall(r'page=(\d+)"[^>]*>\s*(?:Last|last|»)', h); print("  last:", last)

print("===== 3. ESMIS búsqueda SJ_GR113 / DDGS / ethanol =====")
for q in ["sj_gr113", "distillers grain", "ethanol"]:
    h = get(f"https://esmis.nal.usda.gov/search?search_api_fulltext={q.replace(' ','+')}")
    if h:
        print("  pubs:", sorted(set(re.findall(r'href="(/publication/[^"?#]+)"', h)))[:30])

print("===== 4. MARS API sin key =====")
for u in ["https://marsapi.ams.usda.gov/services/v1.2/reports/3616",
          "https://marsapi.ams.usda.gov/services/v1.2/reports"]:
    s = get(u); print("  ", (s or "")[:300])

print("===== 5. mymarketnews filerepo =====")
for u in ["https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=3616",
          "https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=2085",
          "https://mymarketnews.ams.usda.gov/viewReport/3616"]:
    h = get(u)
    if h:
        print("  pdfs:", re.findall(r'href="([^"]+\.(?:pdf|PDF|txt|TXT))"', h)[:10])
