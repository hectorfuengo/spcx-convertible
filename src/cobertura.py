"""Cobertura (note hedge + warrants) y escenarios al vencimiento del convertible de SPCX.

Estructura del caso Molson Coors (Teaching Notes NE90-06-107, Exhibits 1 y 4):
  - El emisor vende un convertible con precio de conversion X (prima sobre la accion).
  - Compra un *note hedge*: call sobre las mismas acciones, con strike X.
  - Vende *warrants*: call sobre las mismas acciones, con strike mayor (prima de 60% en el caso).
  - Efecto neto: la dilucion solo empieza cuando la accion supera el strike de los warrants.

Uso:  python -m src.cobertura [--processed data/processed] [--docs docs/data] [--emision 1000] [--prima-warrant 0.60]
Requiere haber corrido antes src.ingesta y src.valuacion.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bs import call_price  # noqa: E402

NOMINAL = 1000.0


def acciones_en_circulacion_millones(processed: Path) -> tuple[float | None, str | None]:
    """Ultimo dato de 'Common Shares - Outstanding - Total' (millones de acciones) y su fecha."""
    ruta = processed / "financieros_trimestral.json"
    if not ruta.exists():
        return None, None
    for hoja in json.loads(ruta.read_text(encoding="utf-8"))["hojas"].values():
        for c in hoja.get("conceptos", []) if isinstance(hoja, dict) else []:
            if c["concepto"] == "Common Shares - Outstanding - Total":
                validos = {k: v for k, v in c["valores"].items() if v is not None}
                if validos:
                    fecha = max(validos)
                    return validos[fecha], fecha
    return None, None


def cobertura(S: float, prima: float, prima_warrant: float, r: float, sigma: float, sigma_warrant: float,
              T: float, emision_musd: float) -> dict:
    """Costos de la cobertura en millones de USD y acciones en millones."""
    X = S * (1 + prima)
    Kw = S * (1 + prima_warrant)
    bonos_m = emision_musd / NOMINAL                  # millones de bonos
    acciones_m = bonos_m * NOMINAL / X                # millones de acciones subyacentes
    call_hedge = call_price(S, X, T, r, sigma)
    call_warrant = call_price(S, Kw, T, r, sigma_warrant)
    costo_hedge = call_hedge * acciones_m
    ingreso_warrant = call_warrant * acciones_m
    return {
        "precio_conversion": X, "strike_warrants": Kw, "bonos_millones": bonos_m, "acciones_subyacentes_millones": acciones_m,
        "call_note_hedge_por_accion": call_hedge, "call_warrant_por_accion": call_warrant,
        "costo_note_hedge_musd": costo_hedge, "ingreso_warrants_musd": ingreso_warrant,
        "costo_neto_musd": costo_hedge - ingreso_warrant,
        "costo_neto_pct_emision": (costo_hedge - ingreso_warrant) / emision_musd,
        "costo_neto_por_bono": (costo_hedge - ingreso_warrant) / bonos_m,
    }


def escenario(ST: float, S: float, X: float, Kw: float, acciones_m: float, circulacion_m: float | None) -> dict:
    """Resultado al vencimiento si la accion vale ST (pagos en millones de USD)."""
    exceso = max(ST - X, 0.0) * acciones_m            # lo que el convertible paga por encima de la par
    recibe_hedge = max(ST - X, 0.0) * acciones_m      # el note hedge compensa ese exceso
    pago_warrants = max(ST - Kw, 0.0) * acciones_m    # lo que el emisor debe a los tenedores de warrants
    netas = acciones_m * (1 - Kw / ST) if ST > Kw else 0.0   # acciones nuevas netas, con liquidacion neta
    sin_cobertura = acciones_m if ST > X else 0.0
    out = {
        "precio_vencimiento": ST, "variacion_vs_hoy": ST / S - 1,
        "valor_por_bono": max(NOMINAL, ST * NOMINAL / X),
        "convierte": ST > X,
        "exceso_sobre_par_musd": exceso, "recibe_note_hedge_musd": recibe_hedge, "pago_warrants_musd": pago_warrants,
        "costo_neto_vencimiento_musd": pago_warrants + exceso - recibe_hedge,
        "costo_sin_cobertura_musd": exceso,
        "acciones_nuevas_con_cobertura_millones": netas, "acciones_nuevas_sin_cobertura_millones": sin_cobertura,
    }
    if circulacion_m:
        out["dilucion_con_cobertura_pct"] = netas / circulacion_m
        out["dilucion_sin_cobertura_pct"] = sin_cobertura / circulacion_m
    return out


def construir(processed: Path, emision_musd: float = 1000.0, prima_warrant: float = 0.60) -> dict:
    val = json.loads((processed / "valuacion.json").read_text(encoding="utf-8"))
    b = val["base"]
    S, prima, r, sigma, T = b["S"], b["prima"], b["r"], b["sigma"], b["plazo"]
    circ, fecha_circ = acciones_en_circulacion_millones(processed)
    base = cobertura(S, prima, prima_warrant, r, sigma, sigma, T, emision_musd)
    X, Kw, acc = base["precio_conversion"], base["strike_warrants"], base["acciones_subyacentes_millones"]

    precios = sorted({50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500, S, X, Kw})
    escenarios = [escenario(p, S, X, Kw, acc, circ) for p in precios]
    sens = [{"sigma": s, "prima_warrant": p, **cobertura(S, prima, p, r, s, s, T, emision_musd)}
            for s in (0.45, round(sigma, 4), 0.60) for p in (0.50, prima_warrant, 0.70)]
    div = "0" if circ else "n/d"
    return {
        "fecha_valuacion": val["fecha_valuacion"],
        "modelo": "Cobertura según el caso Molson Coors: compra de call (note hedge) en el precio de conversión y venta de call (warrants) "
                  "en un strike mayor. Black-Scholes europeo, sin dividendos. Montos en millones de USD y de acciones.",
        "supuestos": [
            {"nombre": "emision_musd", "valor": emision_musd, "fuente": "Elegida por el equipo (el caso Molson Coors implica ~580 M)",
             "estado": "supuesto del equipo", "nota": "Solo escala los montos totales; los resultados por bono no cambian."},
            {"nombre": "prima_conversion", "valor": prima, "fuente": "Heredada de la valuación base", "estado": "supuesto del equipo", "nota": ""},
            {"nombre": "prima_warrants", "valor": prima_warrant, "fuente": "Tomada del caso Molson Coors (60%, Exhibit 1)", "estado": "supuesto del equipo", "nota": ""},
            {"nombre": "volatilidad", "valor": sigma, "fuente": "Igual que la valuación base; para los warrants se usa la misma",
             "estado": "supuesto del equipo",
             "nota": "El caso usa 21% para los warrants y 23% para el call, con inconsistencias; aquí la IV observada es casi plana entre strikes."},
            {"nombre": "acciones_en_circulacion_millones", "valor": circ, "fuente": "Refinitiv, Common Shares - Outstanding - Total (Clase A + B)",
             "fecha": fecha_circ, "estado": "dato", "nota": ""},
            {"nombre": "dividendos", "valor": 0.0, "fuente": "Refinitiv, Dividends Provided/Paid - Common = 0 en todos los trimestres",
             "estado": "dato", "nota": ""},
        ],
        "base": {"S": S, "prima": prima, "prima_warrant": prima_warrant, "r": r, "sigma": sigma, "plazo": T,
                 "emision_musd": emision_musd, "acciones_circulacion_millones": circ,
                 "dilucion_conversion_total_pct": (acc / circ) if circ else None, **base},
        "escenarios": escenarios,
        "sensibilidad_costo_neto": sens,
        "avisos": [
            "La dilución solo empieza cuando la acción supera el strike de los warrants; entre el precio de conversión y ese strike la cobertura absorbe el exceso.",
            f"Con una emisión de {emision_musd:,.0f} M USD se entregarían {acc:,.2f} M de acciones si hubiera conversión, "
            + (f"{acc / circ * 100:.3f}% de las {circ:,.0f} M en circulación." if circ else "sin dato de acciones en circulación."),
            "Liquidación neta en acciones al vencimiento; no se incluyen costos de transacción, impuestos ni cobertura dinámica.",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--docs", default="docs/data")
    ap.add_argument("--emision", type=float, default=1000.0, help="millones de USD")
    ap.add_argument("--prima-warrant", type=float, default=0.60)
    a = ap.parse_args(argv)
    processed, docs = Path(a.processed), Path(a.docs)
    out = construir(processed, a.emision, a.prima_warrant)
    (processed / "cobertura.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(processed / "cobertura.json", docs / "cobertura.json")
    b = out["base"]
    print(f"Note hedge: {b['costo_note_hedge_musd']:.1f} M | warrants: {b['ingreso_warrants_musd']:.1f} M | "
          f"costo neto: {b['costo_neto_musd']:.1f} M ({b['costo_neto_pct_emision'] * 100:.1f}% de la emision)")
    print(f"Listo. {processed / 'cobertura.json'} y copia en {docs}")


if __name__ == "__main__":
    main()
