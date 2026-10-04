"""Sonda temporal: imprime la fila cruda de New Orleans de algunos reportes, para verificar a mano."""
import sys; sys.path.insert(0, "scripts")
import fetch_ddgs as f
urls = f.links_mymarketnews()
print("total:", len(urls), urls[0], urls[-1])
idx = sorted(set([0, len(urls)//3, 2*len(urls)//3, len(urls)-20, len(urls)-8, len(urls)-1]))
for i in idx:
    t = f.pdf_a_texto(f.descargar(urls[i]))
    print("=====", urls[i])
    for l in t.splitlines():
        if "Report for" in l or l.strip().startswith("New Orleans"):
            print("   |", l.strip())
    print("   parse ->", f.parse_reporte(t))
