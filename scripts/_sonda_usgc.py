"""Sonda temporal (se borra antes de fusionar): ¿trae grains.org el precio de DDGS como texto?"""
import re, subprocess, urllib.request, html as H_
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60); return r.read()
    except Exception as e:
        print(f"[ERR] {url}: {e}"); return b""
def texto(h):
    h = re.sub(r"(?s)<(script|style).*?</\1>", " ", h)
    return re.sub(r"\s+", " ", H_.unescape(re.sub(r"<[^>]+>", " ", h)))
PAT = r"[^.]{0,160}(?:\$\s?\d{2,3}(?:\.\d+)?|\d{3}(?:\.\d+)? ?(?:per|/) ?(?:short |metric )?ton)[^.]{0,120}"
posts = []
for page in [1, 2, 3, 4, 5, 6, 7, 12, 20, 28, 36, 45]:
    u = "https://grains.org/ddgs_report/" + (f"page/{page}/" if page > 1 else "")
    h = get(u).decode("utf-8", "replace")
    ps = list(dict.fromkeys(re.findall(r'href="(https://grains\.org/ddgs_report/[^"/]+/)"', h)))
    ps = [p for p in ps if "/page/" not in p]
    print(f"== listado p{page}: {len(ps)} posts; primero {ps[:1]}")
    posts += ps if page <= 7 else ps[:1]
print("TOTAL posts revisados:", len(posts))
for i, p in enumerate(posts):
    h = get(p).decode("utf-8", "replace"); t = texto(h)
    title = re.search(r"<title>(.*?)</title>", h, re.S); title = H_.unescape(title.group(1).strip()) if title else "?"
    precios = [m.group(0).strip() for m in re.finditer(PAT, t) if re.search(r"DDGS|DDG|distiller", m.group(0), re.I)]
    pdfs = list(dict.fromkeys(re.findall(r'href="([^"]+\.pdf)"', h, re.I)))
    print(f"\n### {title[:80]} | {p}")
    print("  HTML precios:", precios[:3])
    print("  PDFs:", pdfs[:2])
    if pdfs and (i < 3 or i % 8 == 0 or i >= len(posts) - 6):
        b = get(pdfs[0])
        if b.startswith(b"%PDF"):
            open("/tmp/u.pdf", "wb").write(b)
            t2 = subprocess.run(["pdftotext", "-layout", "/tmp/u.pdf", "-"], capture_output=True).stdout.decode("utf-8", "replace")
            imgs = subprocess.run(["pdfimages", "-list", "/tmp/u.pdf"], capture_output=True).stdout.decode().count("\n") - 2
            print(f"  PDF: {len(t2)} chars de texto, {imgs} imágenes")
            for l in t2.splitlines():
                if re.search(r"FOB|Gulf|\$\s?\d{3}|per ton|/MT|/ST", l, re.I):
                    print("   |", l.strip()[:170])
