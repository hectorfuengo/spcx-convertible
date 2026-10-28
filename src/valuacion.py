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
from src.bs import call_price  # noqa: E402

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
    """Prima de conversion con la que un convertible de cupon 0% vale exactamente la par."""
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


def supuesto(nombre, valor, fuente, fecha, estado, nota=""):
    return {"nombre": nombre, "valor": valor, "fuente": fuente, "fecha": fecha, "estado": estado, "nota": nota}


def construir(processed: Path, csv_iv: Path, prima: float = 0.25, plazo: float = 6.0) -> dict:
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
    return {
        "fecha_valuacion": fecha,
        "modelo": "Bono simple + opcion de conversion (Black-Scholes europeo, sin dividendos). Valores por bono de 1,000 USD.",
        "supuestos": [
            supuesto("precio_accion", S, "Refinitiv, cierre", fecha, "dato de mercado"),
            supuesto("prima_conversion", prima, "Tomada del caso Molson Coors (25%)", fecha, "supuesto del equipo"),
            supuesto("plazo_anios", plazo, "Tomado del caso Molson Coors (6 anios)", fecha, "supuesto del equipo"),
            supuesto("tasa_libre_riesgo", r, "UST a 6 anios, interpolado lineal entre 5Y y 7Y", fecha, "calculado"),
            supuesto("tasa_descuento_bono_simple", ytm, "Yield de bonos SPCX a 6 anios (interpolado, bonos con >= 1,000 M vigentes)", fecha, "calculado",
                     "Supone yield semestral. Es deuda senior sin garantia de SPCX, no de un convertible."),
            supuesto("volatilidad", sigma, f"IV de cierre de opciones SPCX, {desc_sigma}", "2026-10-27", "supuesto del equipo",
                     "El dato de mercado llega a 2.1 anios; se extrapola a 6. Leido de pantalla de Refinitiv."),
            supuesto("dividendos", 0.0, "Sin dividendos", fecha, "supuesto del equipo"),
        ],
        "base": {"prima": prima, "sigma": sigma, "r": r, "ytm": ytm, "plazo": plazo, "S": S, **base,
                 "prima_para_cupon_cero": prima_para_cupon_cero(S, r, sigma, plazo, ytm)},
        "sensibilidad_prima_vol": {"primas": primas, "vols": sens_vols, "celdas": celdas,
                                   "nota_vols": "45% y 60% son escenarios; 52.7% es la IV base; la ultima es la volatilidad realizada de SPCX a 60 dias."},
        "sensibilidad_tasa_descuento": celdas_tasa,
        "volatilidades": {
            "implicita_base": sigma,
            "realizada_spcx_total": vols["spcx"]["vol_realizada_total"],
            "realizada_spcx_60d": vols["spcx"]["vol_realizada_60d"],
            "dias_spcx": vols["spcx"]["n_dias"],
            "comparables_realizada_total": {k.upper(): v["vol_realizada_total"] for k, v in vols.items() if k != "spcx"},
        },
        "validacion_molson_coors": {
            "descripcion": "Mismo codigo con los supuestos del caso (S=87.61, prima 25%, r=4.46%, vol 23%, 6 anios, descuento 5.75%)",
            "opcion_por_bono": caso["opcion_por_bono"], "bono_simple_necesario": caso["bono_simple_necesario"],
            "cupon_equilibrio": caso["cupon_equilibrio"],
            "pdf": {"opcion_por_bono": 191.5, "bono_simple": 808.5, "cupon_equilibrio": 0.0193},
        },
        "avisos": [
            "Con la volatilidad implicita de mercado, la opcion vale tanto que el cupon de equilibrio sale negativo: "
            "un convertible de cupon 0% ya valdria mas que la par. En la practica el cupon minimo es 0% y se sube la prima.",
            "La volatilidad realizada de SPCX (desde el 12-jun-2026) es mayor que la implicita; hay pocos dias de historia.",
            "El precio de la accion es el cierre del 26-oct; las IV se leyeron el 27-oct con la accion en 148.58.",
            "Modelo simplificado: opcion europea, sin dividendos, sin riesgo de credito ni clausulas de rescate.",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--iv", default="data/opciones_iv.csv")
    ap.add_argument("--docs", default="docs/data")
    ap.add_argument("--prima", type=float, default=0.25)
    ap.add_argument("--plazo", type=float, default=6.0)
    a = ap.parse_args(argv)
    processed, docs = Path(a.processed), Path(a.docs)
    out = construir(processed, Path(a.iv), a.prima, a.plazo)
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
