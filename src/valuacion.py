"""Valuacion del convertible de SPCX: bono simple + opcion de conversion (Black-Scholes europeo, sin dividendos).

Uso:  python -m src.valuacion [--processed data/processed] [--docs docs/data] [--prima 0.25] [--plazo 6]

Lee data/processed/resumen_mercado.json (lo genera src.ingesta) y data/opciones_iv.csv.
Escribe valuacion.json en data/processed/ y copia a docs/data/ lo que consume el sitio.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bono import cupon_de_equilibrio, valor_bono_simple  # noqa: E402
from src.bs import call_price, put_price  # noqa: E402
from src.ingesta import interpolar  # noqa: E402

NOMINAL = 1000.0
ARCHIVOS_SITIO = ["valuacion.json", "resumen_mercado.json", "precios_spcx.json", "treasuries.json", "bonos.json"]


def valuar(S: float, prima: float, r: float, sigma: float, T: float, ytm: float, nominal: float = NOMINAL) -> dict:
    """Valor de la opcion por bono y cupon de equilibrio. r, sigma, ytm en decimal (0.049 = 4.9%)."""
    X = S * (1 + prima)
    acciones = nominal / X
    call = call_price(S, X, T, r, sigma)
    opcion = call * acciones
    cupon = cupon_de_equilibrio(nominal - opcion, ytm, T, nominal)
    bono_cupon_cero = valor_bono_simple(0.0, ytm, T, nominal)["total"]
    return {
        "precio_conversion": X, "acciones_por_bono": acciones, "call_por_accion": call,
        "opcion_por_bono": opcion, "bono_simple_necesario": nominal - opcion,
        "cupon_equilibrio": cupon,                       # decimal; negativo = ni con 0% de cupon baja de la par
        "valor_con_cupon_cero": bono_cupon_cero + opcion,
    }


def prima_para_cupon_cero(S: float, r: float, sigma: float, T: float, ytm: float) -> float | None:
    """Prima de conversión con la que un convertible de cupon 0% vale exactamente la par."""
    f = lambda p: valuar(S, p, r, sigma, T, ytm)["valor_con_cupon_cero"] - NOMINAL
    if f(0.0) < 0 or f(5.0) > 0:
        return None
    return brentq(f, 0.0, 5.0)


def sigma_implicita_base(ruta_csv: Path, vencimiento: str = "2028-12") -> tuple[float, str]:
    filas = [f for f in csv.DictReader(open(ruta_csv, encoding="utf-8")) if f["vencimiento"] == vencimiento]
    if not filas:
        raise ValueError(f"No hay opciones con vencimiento {vencimiento} en {ruta_csv}")
    iv = sum(float(f["iv_cierre_pct"]) for f in filas) / len(filas)
    return iv / 100, f"promedio call y put, strike {filas[0]['strike']}, vencimiento {vencimiento}"


def volatilidad_implicita(precio: float, S: float, K: float, T: float, r: float, tipo: str) -> float | None:
    """IV (decimal) que reproduce `precio` con Black-Scholes europeo sin dividendos; None si no hay solucion."""
    f = lambda s: (call_price if tipo == "call" else put_price)(S, K, T, r, s) - precio
    try:
        return brentq(f, 0.01, 4.0)
    except ValueError:
        return None


def evidencia_tradingview(ruta_csv: Path, treasuries: dict) -> list[dict]:
    """Recalcula la IV con el punto medio de bid y ask de cada opcion de TradingView.

    La tasa libre de riesgo sale de la curva de Treasuries (interpolada al plazo de cada opcion).
    Se conserva la IV que muestra TradingView para poder compararlas.
    """
    xs = [p["anios"] for p in treasuries["puntos"]]
    ys = [p["yield_pct"] for p in treasuries["puntos"]]
    out = []
    for f in csv.DictReader(open(ruta_csv, encoding="utf-8")):
        T = float(f["dte"]) / 365.0
        r = interpolar(xs, ys, T) / 100
        mid = (float(f["bid"]) + float(f["ask"])) / 2
        iv = volatilidad_implicita(mid, float(f["spot"]), float(f["strike"]), T, r, f["tipo"])
        out.append({"vencimiento": f["vencimiento"], "strike": float(f["strike"]), "tipo": f["tipo"], "punto_medio": mid,
                    "iv_recalculada": iv, "iv_tradingview": float(f["iv_tradingview_pct"]) / 100,
                    "delta": float(f["delta"]) if f["delta"] else None, "tasa_usada": r})
    return out


def supuesto(nombre, valor, fuente, fecha, estado, nota=""):
    return {"nombre": nombre, "valor": valor, "fuente": fuente, "fecha": fecha, "estado": estado, "nota": nota}


def construir(processed: Path, csv_iv: Path, prima: float = 0.25, plazo: float = 6.0, csv_tv: Path | None = None) -> dict:
    res = json.loads((processed / "resumen_mercado.json").read_text(encoding="utf-8"))
    S = res["precio_referencia_spcx"]["valor"]
    r = res["ust_6y_pct"]["valor"] / 100
    ytm = res["yield_bonos_spcx_6y_pct"]["valor"] / 100
    sigma, desc_sigma = sigma_implicita_base(csv_iv)
    fecha = res["fecha_valuacion"]
    vols = res["volatilidad_realizada"]["valor"]

    base = valuar(S, prima, r, sigma, plazo, ytm)
    sens_vols = [0.45, round(sigma, 4), 0.60, round(vols["spcx"]["vol_realizada_60d"], 4)]
    primas = [0.20, 0.25, 0.30]
    celdas = [{"prima": p, "sigma": s, **valuar(S, p, r, s, plazo, ytm)} for p in primas for s in sens_vols]
    tasas = [ytm - 0.015, ytm, ytm + 0.015]
    celdas_tasa = [{"ytm": t, **valuar(S, prima, r, sigma, plazo, t)} for t in tasas]

    caso = valuar(87.61, 0.25, 0.0446, 0.23, 6.0, 0.0575)  # validacion contra el PDF (ver tests/test_molson_coors.py)

    evidencia = None
    if csv_tv is not None and csv_tv.exists():
        ust = json.loads((processed / "treasuries.json").read_text(encoding="utf-8"))
        filas = evidencia_tradingview(csv_tv, ust)
        validas = [f["iv_recalculada"] for f in filas if f["iv_recalculada"]]
        evidencia = {
            "refinitiv": [{"vencimiento": f["vencimiento"], "strike": float(f["strike"]), "tipo": f["tipo"],
                           "iv_cierre": float(f["iv_cierre_pct"]) / 100}
                          for f in csv.DictReader(open(csv_iv, encoding="utf-8"))],
            "tradingview": filas,
            "resumen": {"iv_recalculada_min": min(validas), "iv_recalculada_max": max(validas),
                        "iv_tradingview_min": min(f["iv_tradingview"] for f in filas),
                        "iv_tradingview_max": max(f["iv_tradingview"] for f in filas)},
            "nota": "La IV que muestra TradingView no coincide con la recalculada con Black-Scholes europeo sobre el punto medio de bid y ask "
                    "(posible modelo americano, otra tasa o costo de préstamo de acciones). Los precios bid y ask son consistentes entre sí.",
            "fuente": "TradingView Options chain (leído de pantalla, 3-nov-2026) y Refinitiv Derivatives (27-oct-2026)",
        }
    return {
        "fecha_valuacion": fecha,
        "modelo": "Bono simple + opción de conversión (Black-Scholes europeo, sin dividendos). Valores por bono de 1,000 USD.",
        "supuestos": [
            supuesto("precio_accion", S, "Refinitiv, cierre", fecha, "dato de mercado"),
            supuesto("prima_conversion", prima, "Tomada del caso Molson Coors (25%)", fecha, "supuesto del equipo"),
            supuesto("plazo_anios", plazo, "Tomado del caso Molson Coors (6 años)", fecha, "supuesto del equipo"),
            supuesto("tasa_libre_riesgo", r, "UST a 6 años, interpolado lineal entre 5Y y 7Y", fecha, "calculado"),
            supuesto("tasa_descuento_bono_simple", ytm, "Yield de bonos SPCX a 6 años (interpolado, bonos con >= 1,000 M vigentes)", fecha, "calculado",
                     "Supone yield semestral. Es deuda senior sin garantía de SPCX, no de un convertible."),
            supuesto("volatilidad", sigma, f"IV de cierre de opciones SPCX, {desc_sigma}", "2026-10-27", "supuesto del equipo",
                     "El dato de mercado llega a 2.1 años; se extrapola a 6. Leído de pantalla de Refinitiv y contrastado con precios de TradingView."),
            supuesto("dividendos", 0.0, "Sin dividendos", fecha, "supuesto del equipo"),
        ],
        "base": {"prima": prima, "sigma": sigma, "r": r, "ytm": ytm, "plazo": plazo, "S": S, **base,
                 "prima_para_cupon_cero": prima_para_cupon_cero(S, r, sigma, plazo, ytm)},
        "sensibilidad_prima_vol": {"primas": primas, "vols": sens_vols, "celdas": celdas,
                                   "nota_vols": "45% y 60% son escenarios; 52.7% es la IV base; la última es la volatilidad realizada de SPCX a 60 días."},
        "sensibilidad_tasa_descuento": celdas_tasa,
        "volatilidades": {
            "implicita_base": sigma,
            "realizada_spcx_total": vols["spcx"]["vol_realizada_total"],
            "realizada_spcx_60d": vols["spcx"]["vol_realizada_60d"],
            "dias_spcx": vols["spcx"]["n_dias"],
            "comparables_realizada_total": {k.upper(): v["vol_realizada_total"] for k, v in vols.items() if k != "spcx"},
        },
        "evidencia_volatilidad": evidencia,
        "calificaciones": {
            "emisor": [
                {"agencia": "Moody's", "calificacion": "Baa1", "perspectiva": "estable", "fecha": "2026-06-19"},
                {"agencia": "Fitch", "calificacion": "BBB+", "perspectiva": "estable", "fecha": "2026-06-19"},
                {"agencia": "S&P", "calificacion": "BBB", "perspectiva": "estable", "fecha": "2026-06-19"},
            ],
            "fuente": "Euronews, 19-jun-2026 (primera calificación de las tres agencias). Moody's coincide con Refinitiv (peers_balance).",
            "estado": "dato (fuente periodistica)",
            "nota": "No se encontró si la calificación de S&P es de emisor o de emisión. CDS: no disponible.",
        },
        "validacion_molson_coors": {
            "descripcion": "Mismo código con los supuestos del caso (S=87.61, prima 25%, r=4.46%, vol 23%, 6 años, descuento 5.75%)",
            "opcion_por_bono": caso["opcion_por_bono"], "bono_simple_necesario": caso["bono_simple_necesario"],
            "cupon_equilibrio": caso["cupon_equilibrio"],
            "pdf": {"opcion_por_bono": 191.5, "bono_simple": 808.5, "cupon_equilibrio": 0.0193},
        },
        "avisos": [
            "Con la volatilidad implícita de mercado, la opción vale tanto que el cupón de equilibrio sale negativo: "
            "un convertible de cupón 0% ya valdría más que la par. En la práctica el cupón mínimo es 0% y se sube la prima.",
            "La volatilidad realizada de SPCX (desde el 12-jun-2026) es mayor que la implícita; hay pocos días de historia.",
            "El precio de la acción es el cierre del 26-oct; las IV de Refinitiv se leyeron el 27-oct con la acción en 148.58 y las de TradingView el 3-nov con la acción en 141.31.",
            "Modelo simplificado: opción europea, sin dividendos, sin riesgo de crédito ni cláusulas de rescate.",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--iv", default="data/opciones_iv.csv")
    ap.add_argument("--tv", default="data/opciones_tradingview.csv")
    ap.add_argument("--docs", default="docs/data")
    ap.add_argument("--prima", type=float, default=0.25)
    ap.add_argument("--plazo", type=float, default=6.0)
    a = ap.parse_args(argv)
    processed, docs = Path(a.processed), Path(a.docs)
    out = construir(processed, Path(a.iv), a.prima, a.plazo, Path(a.tv))
    (processed / "valuacion.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    for n in ARCHIVOS_SITIO:
        shutil.copy(processed / n, docs / n)
    b = out["base"]
    print(f"Opcion por bono: {b['opcion_por_bono']:.1f} | cupon de equilibrio: {b['cupon_equilibrio'] * 100:.2f}% | "
          f"valor con cupon 0%: {b['valor_con_cupon_cero']:.1f} | prima para cupon 0%: {b['prima_para_cupon_cero']}")
    print(f"Listo. {processed / 'valuacion.json'} y copia en {docs}")


if __name__ == "__main__":
    main()
