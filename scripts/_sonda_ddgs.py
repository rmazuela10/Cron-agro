"""Sonda temporal: busca archivo de AMS_3616 posterior a sep-2025 en MyMarketNews."""
import re, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "*/*"}
def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120)
        b = r.read().decode("utf-8", "replace"); print(f"[{r.status}] {url} {len(b)}b"); return b
    except Exception as e:
        print(f"[ERR] {url}: {e}"); return ""
M = "https://mymarketnews.ams.usda.gov"
for q in ["field_slug_id_value=3616", "slug_id=3616", "field_slug_id=3616", "combine=3616", "title=3616",
          "field_report_slug_id_value=3616", "search=ams_3616", "keys=3616"]:
    h = get(f"{M}/filerepo/reports?{q}")
    hits = re.findall(r'href="([^"]*ams_3616[^"]*)"', h)
    print("   hits:", len(hits), hits[:3])
    if h and q == "slug_id=3616":
        print("   forms:", sorted(set(re.findall(r'name="([^"]+)"', h)))[:40])
for u in [f"{M}/services/v1.1/public/listPublishedReports/reportDate?slugId=3616",
          f"{M}/public_data?slug_id=3616",
          f"{M}/services/v1.2/reports/3616",
          f"{M}/viewReport/3616"]:
    h = get(u); print("   ", h[:400].replace("\n"," "))
    print("   hits:", re.findall(r'(https?://[^"\s]*3616[^"\s]*)', h)[:10])
