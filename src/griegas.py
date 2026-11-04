"""Griegas: de las opciones listadas (LSEG vs cálculo propio) y del convertible con su cobertura.

Uso:  python -m src.griegas [--processed data/processed] [--csv data/opciones_refinitiv_griegas.csv] [--docs docs/data]
Requiere haber corrido antes src.valuacion y src.cobertura.

Unidades (las mismas que muestra LSEG, confirmadas contra el cálculo propio):
  delta: por acción; gamma: delta por 1 USD; vega: USD por 1 punto de volatilidad;
  theta: USD por día calendario; rho: USD por 1 punto de tasa.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bs import call_price, greeks, put_price  # noqa: E402
from src.ingesta import interpolar  # noqa: E402
from src.valuacion import volatilidad_implicita  # noqa: E402

CAMPOS_LSEG = ("delta", "gamma", "vega", "theta")


def griegas_unidades(S: float, K: float, T: float, r: float, sigma: float, tipo: str = "call") -> dict:
    """Griegas de Black-Scholes en las unidades de LSEG (vega por punto, theta por día, rho por punto)."""
    g = greeks(S, K, T, r, sigma, tipo)
    return {"delta": g["delta"], "gamma": g["gamma"], "vega": g["vega"] / 100, "theta": g["theta"] / 365, "rho": g["rho"] / 100}


def _num(x: str) -> float | None:
    return float(x) if x not in ("", None) else None


def opciones_listadas(ruta_csv: Path, treasuries: dict) -> list[dict]:
    xs = [p["anios"] for p in treasuries["puntos"]]
    ys = [p["yield_pct"] for p in treasuries["puntos"]]
    out = []
    for f in csv.DictReader(open(ruta_csv, encoding="utf-8")):
        S, K, T = float(f["spot"]), float(f["strike"]), float(f["dte"]) / 365.0
        r = interpolar(xs, ys, T) / 100
        bid, ask = float(f["bid"]), float(f["ask"])
        mid = (bid + ask) / 2
        iv_lseg = _num(f["iv_mid_pct"])
        lseg = {k: _num(f[k]) for k in CAMPOS_LSEG}
        iv_precio = volatilidad_implicita(mid, S, K, T, r, f["tipo"])
        # con IV de LSEG si la hay (para comparar con sus griegas); si no, con la IV que reproduce el punto medio
        sigma = iv_lseg / 100 if iv_lseg is not None else iv_precio
        propias = griegas_unidades(S, K, T, r, sigma, f["tipo"]) if sigma else None
        dif = {k: (propias[k] - lseg[k]) if (propias and lseg[k] is not None) else None for k in CAMPOS_LSEG}
        out.append({
            "vencimiento": f["vencimiento"], "tipo": f["tipo"], "strike": K, "bid": bid, "ask": ask, "punto_medio": mid,
            "volumen": _num(f["volumen"]), "interes_abierto": _num(f["interes_abierto"]),
            "iv_lseg": iv_lseg / 100 if iv_lseg is not None else None, "iv_punto_medio": iv_precio, "tasa_usada": r,
            "lseg": lseg if any(v is not None for v in lseg.values()) else None,
            "propias": propias, "dif": dif if any(v is not None for v in dif.values()) else None,
            "origen_griegas": "LSEG y cálculo propio" if iv_lseg is not None else "cálculo propio (LSEG no las mostró)",
            "fecha_captura": f["fecha_captura"], "hora_aprox_mty": f["hora_captura_mty"], "spot": S,
        })
    return out


def resumen_diferencias(filas: list[dict]) -> dict:
    """Diferencia relativa media (propias vs LSEG) por griega, por vencimiento y tipo."""
    res: dict[str, dict] = {}
    for f in filas:
        if not f["lseg"]:
            continue
        clave = f"{f['tipo']} {f['vencimiento']}"
        for k in CAMPOS_LSEG:
            if f["lseg"][k]:
                res.setdefault(clave, {}).setdefault(k, []).append(f["propias"][k] / f["lseg"][k] - 1)
    return {c: {k: {"media": sum(v) / len(v), "max_abs": max(abs(x) for x in v), "n": len(v)} for k, v in d.items()} for c, d in res.items()}


def posicion(S: float, K: float, T: float, r: float, sigma: float, acciones_m: float, signo: int, tipo: str = "call") -> dict:
    """Griegas de una posición en millones de acciones (signo +1 larga, -1 corta). Montos en millones de USD."""
    g = griegas_unidades(S, K, T, r, sigma, tipo)
    c = signo * acciones_m
    return {"delta_acciones_m": g["delta"] * c, "delta_usd_m": g["delta"] * c * S, "gamma_acciones_m_por_usd": g["gamma"] * c,
            "vega_musd_por_punto": g["vega"] * c, "theta_musd_por_dia": g["theta"] * c, "rho_musd_por_punto": g["rho"] * c}


def convertible(processed: Path) -> dict:
    cob = json.loads((processed / "cobertura.json").read_text(encoding="utf-8"))
    b = cob["base"]
    S, r, sig, T = b["S"], b["r"], b["sigma"], b["plazo"]
    X, Kw, acc = b["precio_conversion"], b["strike_warrants"], b["acciones_subyacentes_millones"]
    # posiciones desde el punto de vista del emisor
    conv = posicion(S, X, T, r, sig, acc, -1)        # opción de conversión vendida a los tenedores
    hedge = posicion(S, X, T, r, sig, acc, +1)       # note hedge comprado
    warr = posicion(S, Kw, T, r, sig, acc, -1)       # warrants vendidos
    llaves = conv.keys()
    neto = {k: conv[k] + hedge[k] + warr[k] for k in llaves}
    sin = dict(conv)
    por_bono = griegas_unidades(S, X, T, r, sig, "call")
    bonos_m = b["bonos_millones"]
    # delta de la posición en función del precio
    grid = sorted({50, 75, 100, 125, 150, 175, 200, 250, 300, 400, round(S, 2), round(X, 3), round(Kw, 3)})
    curva = []
    for p in grid:
        pc, ph, pw = (posicion(p, X, T, r, sig, acc, -1), posicion(p, X, T, r, sig, acc, +1), posicion(p, Kw, T, r, sig, acc, -1))
        curva.append({"precio": p,
                      "delta_sin_cobertura": pc["delta_acciones_m"],
                      "delta_con_cobertura": pc["delta_acciones_m"] + ph["delta_acciones_m"] + pw["delta_acciones_m"],
                      "gamma_sin_cobertura": pc["gamma_acciones_m_por_usd"],
                      "gamma_con_cobertura": pc["gamma_acciones_m_por_usd"] + ph["gamma_acciones_m_por_usd"] + pw["gamma_acciones_m_por_usd"]})
    return {
        "parametros": {"S": S, "X": X, "Kw": Kw, "r": r, "sigma": sig, "plazo": T, "acciones_millones": acc, "emision_musd": b["emision_musd"],
                       "bonos_millones": bonos_m},
        "por_accion": {"opcion_conversion": por_bono, "warrant": griegas_unidades(S, Kw, T, r, sig, "call")},
        "por_bono": {k: v * (1000.0 / X) for k, v in por_bono.items()},
        "posiciones": {"opcion_conversion_vendida": conv, "note_hedge_comprado": hedge, "warrants_vendidos": warr,
                       "emisor_con_cobertura": neto, "emisor_sin_cobertura": sin},
        "curva_precio": curva,
        "estado": "calculado",
    }


def construir(processed: Path, csv_lseg: Path) -> dict:
    ust = json.loads((processed / "treasuries.json").read_text(encoding="utf-8"))
    filas = opciones_listadas(csv_lseg, ust)
    return {
        "fecha_captura": filas[0]["fecha_captura"] if filas else None,
        "unidades": {"delta": "por acción", "gamma": "delta por 1 USD", "vega": "USD por 1 punto de volatilidad",
                     "theta": "USD por día calendario", "rho": "USD por 1 punto de tasa"},
        "opciones": filas,
        "diferencias": resumen_diferencias(filas),
        "convertible": convertible(processed),
        "avisos": [
            "Las griegas de las opciones listadas se leyeron de pantalla de LSEG Workspace el 3-nov-2026 (hora aproximada de Monterrey en la tabla); "
            "el resto del dashboard usa precios del 26-oct.",
            "LSEG no mostró IV ni griegas para los puts de ene-2029 ni para los calls de 115–140 de dic-2028; las de los puts son cálculo propio "
            "con la IV que reproduce el punto medio de bid y ask.",
            "El cálculo propio usa Black-Scholes europeo sin dividendos y la tasa de la curva UST al plazo de cada opción; las opciones listadas son americanas.",
            "En LSEG, el vega salta de forma irregular en algunos strikes (por ejemplo 180 y 220 en ene-2029) sin que cambien otras griegas; "
            "no se corrigió. El cálculo propio es suave.",
            "Las griegas del convertible usan la volatilidad base (52.65%) y los mismos supuestos de la valuación; son del emisor (signo: larga +, corta −).",
        ],
        "fuente": "LSEG Workspace (opciones listadas) y cálculo propio (Black-Scholes)",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--csv", default="data/opciones_refinitiv_griegas.csv")
    ap.add_argument("--docs", default="docs/data")
    a = ap.parse_args(argv)
    processed, docs = Path(a.processed), Path(a.docs)
    out = construir(processed, Path(a.csv))
    (processed / "griegas.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(processed / "griegas.json", docs / "griegas.json")
    n = out["convertible"]["posiciones"]["emisor_con_cobertura"]
    print(f"{len(out['opciones'])} opciones | delta neta con cobertura: {n['delta_acciones_m']:.3f} M acciones")
    print(f"Listo. {processed / 'griegas.json'} y copia en {docs}")


if __name__ == "__main__":
    main()
