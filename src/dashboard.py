"""Arma docs/index.html (un solo archivo autocontenido) a partir de la plantilla y los datos.

Uso:  python -m src.dashboard [--docs docs]

Lee docs/index.src.html, los JSON de docs/data/ y las herramientas de docs/tools/ (árboles y GARCH de la tarea) y escribe docs/index.html
con todo incrustado: abre igual desde GitHub Pages que haciendo doble clic en el archivo. También copia data/empresa.json a docs/data/.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DATOS = ["valuacion", "resumen_mercado", "precios_spcx", "treasuries", "bonos", "cobertura", "analisis", "griegas", "empresa", "competidores", "arboles", "swaps"]
HERRAMIENTAS = {"arboles": "arboles_spcx.html", "garch": "garch_spcx.html"}

# Alinea los colores de las herramientas con los del dashboard (claro y oscuro)
TEMA = """<style>
:root{--bg:#f6f7f9;--panel:#fff;--ink:#14181f;--muted:#5d6675;--line:#e2e5ea;--grid:#e8ebf0;--accent:#c27a1a;--c1:#c27a1a;--c2:#1f4fd8;--soft:#f1f3f6}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--panel:#171b23;--ink:#eceff4;--muted:#9aa4b5;--line:#2a303b;--grid:#262b35;--accent:#e39a3b;--c1:#e39a3b;--c2:#7da2ff;--soft:#1d222c}}
body{background:transparent}.wrap{padding-top:12px}header .tag{display:none}header h1{font-size:20px}header p{font-size:13.5px}
</style>"""


def _js(obj) -> str:
    """JSON seguro para incrustar dentro de un <script>."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\!--")


def construir(docs: Path, raiz: Path) -> Path:
    shutil.copy(raiz / "data" / "empresa.json", docs / "data" / "empresa.json")
    plantilla = (docs / "index.src.html").read_text(encoding="utf-8")
    datos = {f: json.loads((docs / "data" / f"{f}.json").read_text(encoding="utf-8")) for f in DATOS}
    herr = {}
    for clave, archivo in HERRAMIENTAS.items():
        html = (docs / "tools" / archivo).read_text(encoding="utf-8")
        herr[clave] = html.replace("</head>", TEMA + "</head>", 1)
    for marca in ("/*__DATA__*/", "/*__TOOLS__*/"):
        if plantilla.count(marca) != 1:
            raise SystemExit(f"La plantilla debe tener exactamente una marca {marca}")
    salida = plantilla.replace("/*__DATA__*/", "window.__DATA__=" + _js(datos) + ";").replace("/*__TOOLS__*/", "window.__TOOLS__=" + _js(herr) + ";")
    ruta = docs / "index.html"
    ruta.write_text(salida, encoding="utf-8")
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="docs")
    a = ap.parse_args(argv)
    docs = Path(a.docs).resolve()
    ruta = construir(docs, docs.parent)
    print("Escrito", ruta, f"({ruta.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
