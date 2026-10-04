"""Sonda temporal: página 2 de PDFs de grains.org (texto + imagen) para varias épocas."""
import re, subprocess, urllib.request, os
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
def get(u):
    try: return urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60).read()
    except Exception as e: print("[ERR]", u, e); return b""
os.makedirs("_sonda/out", exist_ok=True)
for page in [1, 9, 18, 27, 36, 41, 43]:
    u = "https://grains.org/ddgs_report/" + (f"page/{page}/" if page > 1 else "")
    h = get(u).decode("utf-8", "replace")
    ps = [p for p in dict.fromkeys(re.findall(r'href="(https://grains\.org/ddgs_report/[^"/]+/)"', h)) if "/page/" not in p and "/feed/" not in p]
    p = ps[0]; hp = get(p).decode("utf-8", "replace")
    pdfs = list(dict.fromkeys(re.findall(r'href="([^"]+\.pdf)"', hp, re.I)))
    title = re.search(r"<title>(.*?)</title>", hp, re.S).group(1)[:70]
    print(f"\n######## listado p{page}: {title} | {pdfs[:1]}")
    if not pdfs: continue
    b = get(pdfs[0]); fn = f"_sonda/out/p{page}.pdf"; open(fn, "wb").write(b)
    t = subprocess.run(["pdftotext", "-layout", "-f", "2", "-l", "2", fn, "-"], capture_output=True).stdout.decode("utf-8", "replace")
    print(t[:3500])
    print(subprocess.run(["pdfimages", "-f", "2", "-l", "2", "-list", fn], capture_output=True).stdout.decode()[:600])
    subprocess.run(["pdftoppm", "-f", "2", "-l", "2", "-r", "70", "-png", fn, f"_sonda/out/p{page}"])
    os.remove(fn)
