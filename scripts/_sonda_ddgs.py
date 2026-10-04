"""Sonda temporal (se borra antes de fusionar): explora fuentes USDA desde el runner."""
import re, subprocess, urllib.request, html as H_
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
B = "https://esmis.nal.usda.gov"

def get(url, binary=False):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60)
        b = r.read()
        return b if binary else b.decode("utf-8", "replace")
    except Exception as e:
        print(f"[ERR] {url}: {e}"); return None

def pdftext(b, name):
    open(f"/tmp/{name}.pdf", "wb").write(b)
    subprocess.run(["pdftotext", "-layout", f"/tmp/{name}.pdf", f"/tmp/{name}.txt"], check=True)
    return open(f"/tmp/{name}.txt").read()

def grep(t, pats, ctx=0):
    lines = t.splitlines()
    for i, l in enumerate(lines):
        if re.search(pats, l, re.I):
            for j in range(max(0, i-ctx), min(len(lines), i+ctx+1)):
                print("   |", lines[j].rstrip()[:200])

def releases(h):
    # pares (fecha, link) — imprime el texto plano alrededor de cada link
    out = []
    for m in re.finditer(r'href="(/sites/default/release-files/[^"]+)"', h):
        pre = re.sub(r"<[^>]+>", " ", h[max(0, m.start()-700):m.start()])
        pre = re.sub(r"\s+", " ", H_.unescape(pre))[-120:]
        out.append((pre, m.group(1)))
    return out

for slug in ["national-weekly-ethanol-report", "national-daily-ethanol-report-pdf"]:
    print(f"===== {slug} =====")
    h = get(f"{B}/publication/{slug}?page=0")
    if not h: continue
    pages = [int(x) for x in re.findall(r"[?&]page=(\d+)", h)]
    last = max(pages) if pages else 0
    print("  ultima pagina:", last)
    for p in [0, last]:
        hp = get(f"{B}/publication/{slug}?page={p}")
        rs = releases(hp or "")
        print(f"  -- page {p}: {len(rs)} links")
        for pre, l in rs[:3] + rs[-3:]:
            print("    ", repr(pre[-90:]), l)

print("===== actual: Export Point =====")
t = pdftext(get("https://www.ams.usda.gov/mnreports/ams_3616.pdf", True), "actual")
grep(t, r"Export Point|New Orleans|Gulf|NOLA", ctx=2)

print("===== weekly más antiguo en ESMIS =====")
h = get(f"{B}/publication/national-weekly-ethanol-report?page=0")
last = max(int(x) for x in re.findall(r"[?&]page=(\d+)", h))
rs = [r for r in releases(get(f"{B}/publication/national-weekly-ethanol-report?page={last}") or "") if "3616" in r[1].upper()]
for pre, l in rs[-2:]:
    b = get(B + l, True)
    if b:
        t = pdftext(b, "viejo"); print(" archivo:", l); grep(t, r"Report for|Export Point|New Orleans|Gulf|NOLA", ctx=1)

print("===== diarios PDF antiguos (2017-2021): filas NOLA/Gulf =====")
h = get(f"{B}/publication/national-daily-ethanol-report-pdf?page=0")
if h:
    last = max(int(x) for x in re.findall(r"[?&]page=(\d+)", h))
    for p in sorted(set([last, last*3//4, last//2, last//4])):
        rs = releases(get(f"{B}/publication/national-daily-ethanol-report-pdf?page={p}") or "")
        rs = [r for r in rs if r[1].upper().endswith(".PDF")]
        if not rs: continue
        b = get(B + rs[0][1], True)
        if b:
            t = pdftext(b, f"d{p}"); print(f" page {p}:", rs[0][1]); grep(t, r"Ethanol Report|20\d\d$|NOLA|Gulf|New Orleans|Vessel|Barge", ctx=0)
