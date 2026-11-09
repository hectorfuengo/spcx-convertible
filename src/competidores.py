"""Competidores de SPCX: indicadores de mercado, rentabilidad, apalancamiento y precios (base 100).

Uso:  python -m src.competidores [--processed data/processed] [--docs docs/data] [--corte 2026-10-26]
Requiere haber corrido antes src.ingesta y src.analisis. Escribe competidores.json y lo copia a docs/data/.

Todos los rendimientos y la correlación se calculan hasta la misma fecha de corte (por defecto 2026-10-26, la fecha de los
exportes de Refinitiv), aunque algún archivo de precios llegue más lejos.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from math import log, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ticker -> (archivo de precios, nombre corto, qué hace, por qué es comparable, grupo)
EMPRESAS = {
    "SPCX": ("precios_spcx", "SpaceX (SPCX)", "Lanzamiento reutilizable (Falcon, Starship), internet satelital (Starlink) y, desde la absorción de xAI, inteligencia artificial y la red social X.", "Emisora del caso.", "Emisor"),
    "RKLB": ("precios_rklb", "Rocket Lab", "Lanzamiento de cohetes pequeños (Electron), cohete mediano Neutron en desarrollo y sistemas espaciales (satélites y componentes).", "Competidor directo en lanzamiento y manufactura espacial; empresa de crecimiento, aún con pérdidas.", "Espacio de crecimiento"),
    "AVAV": ("precios_avav", "AeroVironment", "Sistemas aéreos no tripulados y munición merodeadora para defensa; con BlueHalo suma espacio, ciberseguridad y energía dirigida.", "Defense-tech de crecimiento con cartera de gobierno de EE. UU., como SPCX.", "Defense-tech"),
    "KTOS": ("precios_ktos", "Kratos", "Drones tácticos y aeronaves objetivo, hipersónicos, electrónica de defensa y sistemas espaciales y de satélites.", "Defense-tech de crecimiento; valuación alta frente a sus utilidades.", "Defense-tech"),
    "NOC": ("precios_noc", "Northrop Grumman", "Aeronaves (bombardero B-21), misiles estratégicos, sistemas espaciales (satélites y propulsión sólida) y sistemas de misión.", "Contratista tradicional de defensa y espacio; referencia de negocio maduro con calificación A1.", "Contratista tradicional"),
    "GD": ("precios_gd", "General Dynamics", "Aviones de negocios Gulfstream, submarinos y buques (Marine Systems), vehículos de combate y tecnología de información para defensa.", "Contratista tradicional de defensa; referencia de bajo apalancamiento y volatilidad baja.", "Contratista tradicional"),
    "BA": ("precios_ba", "Boeing", "Aviones comerciales, defensa, espacio y seguridad (incluye SLS y Starliner) y servicios globales.", "Contratista aeroespacial muy apalancado (Baa3); es la empresa que usaremos para la sección de swaps.", "Contratista tradicional"),
}
ORDEN = list(EMPRESAS)
VENTANAS = {"1M": 21, "3M": 63, "6M": 126, "1A": 252}


def _cargar(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _serie(processed: Path, archivo: str, corte: str) -> list[tuple[str, float]]:
    d = _cargar(processed / f"{archivo}.json")
    return [(x["fecha"], float(x["cierre"])) for x in d["datos"] if x["fecha"] <= corte and x.get("cierre")]


def _ret(s: list[tuple[str, float]], n: int):
    return s[-1][1] / s[-1 - n][1] - 1 if len(s) > n else None


def _max_dd(s: list[tuple[str, float]]) -> float:
    pico, peor = s[0][1], 0.0
    for _, c in s:
        pico = max(pico, c)
        peor = min(peor, c / pico - 1)
    return peor


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return cov / sqrt(va * vb)


def _sub(fila: dict, columnas: dict, valores: dict):
    for k, col in columnas.items():
        fila[k] = valores.get(col)


def construir(processed: Path, corte: str) -> dict:
    an = _cargar(processed / "analisis.json")
    comp = {f["ticker"]: f for f in an["comparables"]["filas"]}
    pb = {e["Identifier (RIC)"].split(".")[0]: e for e in _cargar(processed / "peers_balance.json")["empresas"]}
    pr = {e["Identifier (RIC)"].split(".")[0]: e for e in _cargar(processed / "peers.json")["empresas"]}
    vol = _cargar(processed / "resumen_mercado.json")["volatilidad_realizada"]["valor"]

    series = {t: _serie(processed, EMPRESAS[t][0], corte) for t in ORDEN}
    ini_spcx = series["SPCX"][0][0]
    filas = []
    for t in ORDEN:
        s = series[t]
        c, b, p = comp[t], pb.get(t, {}), pr.get(t, {})
        fila = {
            "ticker": t, "nombre": EMPRESAS[t][1], "que_hace": EMPRESAS[t][2], "por_que": EMPRESAS[t][3], "grupo": EMPRESAS[t][4],
            "es_spcx": t == "SPCX",
            "precio": s[-1][1], "fecha_precio": s[-1][0], "desde": s[0][0], "n_dias": len(s),
            "cap_musd": c["cap_musd"], "cambio_1d": p.get("1-day Price PCT Change"),
            "retornos": {k: _ret(s, n) for k, n in VENTANAS.items()},
            "retorno_total": s[-1][1] / s[0][1] - 1, "max_drawdown": _max_dd(s),
            "vol_realizada": vol[t.lower()]["vol_realizada_total"], "vol_60d": vol[t.lower()]["vol_realizada_60d"],
            "pe": c["pe"], "pb": p.get("Price To Book Value Per Share(Time Series Ratio)"), "ev_ebitda": c["ev_ebitda"],
            "ev_musd": (p.get("Enterprise Value (FY0, usd)") or 0) / 1e6 or None,
            "margen_neto": c["margen_neto"], "roe": c["roe"], "crecimiento_5a_pct": c["crecimiento_ingresos_5a_pct"],
            "deuda_capital": c["deuda_capital"], "deuda_neta_ebitda_fy1": c["deuda_neta_ebitda_fy1"],
            "ebitda_sobre_intereses": c["ebitda_sobre_intereses"], "razon_circulante": c["razon_circulante"],
            "quick": b.get("Quick Ratio (FI0)"), "dias_cobro": b.get("Average Receivables Collection Days (FY0)"),
            "caja_musd": (b.get("Cash & Short Term Investments (FY0, usd)") or 0) / 1e6 or None,
            "deuda_musd": (b.get("Total Debt - Actual (FY0, usd)") or 0) / 1e6 or None,
            "fcf_musd": None if b.get("Free Cash Flow") is None else b["Free Cash Flow"] / 1e6,
            "beta": c["beta_5a"], "dividendo": c["rendimiento_dividendo"], "calificacion": c["calificacion_emisor"],
        }
        if t == "SPCX" and fila["deuda_musd"] is None:  # Refinitiv no trae la deuda FY0 de SPCX: se toma del balance anual (FY2025)
            fila["deuda_musd"] = an["razones"]["anual"][-1]["cifras"]["deuda_total"]
        filas.append(fila)

    # precios base 100: (a) 2 años de los comparables, semanal; (b) desde el listado de SPCX, diario, todos
    inicio_comun = max(series[t][0][0] for t in ORDEN if t != "SPCX")  # el comparable con historia más corta fija el inicio
    fechas_a = [f for f, _ in series["NOC"] if f >= inicio_comun]
    paso = 5
    idx_a = list(range(0, len(fechas_a), paso))
    if idx_a[-1] != len(fechas_a) - 1:
        idx_a.append(len(fechas_a) - 1)
    comunes = {t: dict(series[t]) for t in ORDEN}
    base_a = {t: comunes[t].get(fechas_a[0]) for t in ORDEN if t != "SPCX"}
    precios_2a = {
        "fechas": [fechas_a[i] for i in idx_a],
        "series": {t: [None if comunes[t].get(fechas_a[i]) is None else round(100 * comunes[t][fechas_a[i]] / base_a[t], 2) for i in idx_a] for t in ORDEN if t != "SPCX"},
    }
    fechas_b = [f for f, _ in series["SPCX"]]
    base_b = {t: comunes[t].get(ini_spcx) or comunes[t][min(f for f in comunes[t] if f >= ini_spcx)] for t in ORDEN}
    precios_listado = {
        "fechas": fechas_b,
        "series": {t: [None if comunes[t].get(f) is None else round(100 * comunes[t][f] / base_b[t], 2) for f in fechas_b] for t in ORDEN},
    }

    # correlación de rendimientos log diarios desde el listado de SPCX
    rets = {}
    for t in ORDEN:
        px = comunes[t]
        rets[t] = [log(px[fechas_b[i]] / px[fechas_b[i - 1]]) for i in range(1, len(fechas_b))]
    corr = {t: _corr(rets["SPCX"], rets[t]) for t in ORDEN if t != "SPCX"}

    return {
        "corte": corte, "filas": filas, "precios_2a": precios_2a, "precios_listado": precios_listado,
        "correlacion_con_spcx": corr, "n_rendimientos_corr": len(fechas_b) - 1, "inicio_spcx": ini_spcx,
        "notas": [
            f"Rendimientos, volatilidad y correlación calculados con cierres hasta {corte}; el archivo de GD llega más lejos pero se recortó para alinear fechas.",
            "SPCX cotiza desde " + ini_spcx + ": no tiene retornos a 6 meses ni 1 año y su beta y ROE no están disponibles en Refinitiv.",
            "Los indicadores fundamentales usan periodos distintos (FY0, FY1, TTM); revisar la nota de comparables antes de compararlos uno a uno.",
            "El ROE de BA (≈150 %) y su deuda / capital (≈991 %) se distorsionan por un capital contable casi nulo.",
            "Las descripciones de negocio son conocimiento general y no salen de Refinitiv; verificarlas contra el 10-K de cada empresa.",
        ],
        "fuente": "Refinitiv (peers, peers_balance, precios), exportes del 2026-10-26; cálculos propios en src/competidores.py",
        "estado": "dato / calculado",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--docs", default="docs/data")
    ap.add_argument("--corte", default="2026-10-26")
    a = ap.parse_args(argv)
    date.fromisoformat(a.corte)
    processed = Path(a.processed)
    d = construir(processed, a.corte)
    ruta = processed / "competidores.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(ruta, docs / "competidores.json")
    print("Escrito", ruta)


if __name__ == "__main__":
    main()
