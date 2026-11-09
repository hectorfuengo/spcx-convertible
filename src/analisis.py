"""Razones financieras, estructura de deuda y comparables de SPCX a partir de data/processed/.

Uso:  python -m src.analisis [--processed data/processed] [--docs docs/data]
Requiere haber corrido antes src.ingesta. Escribe analisis.json y lo copia a docs/data/.
Montos en millones de USD salvo que se indique otra unidad.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CONCEPTOS = {
    "ingresos": "Revenue from Business Activities - Total",
    "ebitda": "Earnings before Interest, Taxes, Depreciation & Amortization (EBITDA)",
    "ebit": "Earnings before Interest & Taxes (EBIT)",
    "utilidad_neta": "Net Income after Tax",
    "intereses": "Interest Expense",
    "activos": "Total Assets",
    "pasivos": "Total Liabilities",
    "capital": "Total Shareholders' Equity - including Minority Interest & Hybrid Debt",
    "activo_circulante": "Total Current Assets",
    "pasivo_circulante": "Total Current Liabilities",
    "deuda_total": "Debt - Total",
    "deuda_cp": "Short-Term Debt & Current Portion of Long-Term Debt",
    "deuda_lp": "Long-Term Debt excluding Capitalized Leases",
    "efectivo": "Cash & Cash Equivalents - Total",
    "deuda_neta": "Net Debt",
}


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def serie(fin: dict, concepto: str) -> dict[str, float | None]:
    """Valores por periodo del primer concepto con ese nombre en cualquier hoja."""
    for hoja in fin["hojas"].values():
        if not isinstance(hoja, dict):
            continue
        for c in hoja.get("conceptos", []):
            if c["concepto"] == concepto:
                return c["valores"]
    return {}


def _div(a, b):
    return None if a is None or b in (None, 0) else a / b


def razones_periodo(fin: dict, periodo: str, factor_anual: float | None = None) -> dict:
    """Cifras base y razones de un periodo. `factor_anual` (4 para un trimestre) solo se usa en deuda neta / EBITDA."""
    v = {k: serie(fin, c).get(periodo) for k, c in CONCEPTOS.items()}
    if v["deuda_total"] is None and v["deuda_cp"] is not None and v["deuda_lp"] is not None:
        v["deuda_total"] = v["deuda_cp"] + v["deuda_lp"]
    ebitda_anual = v["ebitda"] * factor_anual if (v["ebitda"] is not None and factor_anual) else v["ebitda"]
    r = {
        "deuda_sobre_activos": _div(v["deuda_total"], v["activos"]),
        "deuda_sobre_capital": _div(v["deuda_total"], v["capital"]),
        "pasivos_sobre_activos": _div(v["pasivos"], v["activos"]),
        "razon_circulante": _div(v["activo_circulante"], v["pasivo_circulante"]),
        "cobertura_intereses": _div(v["ebit"], v["intereses"]),
        "deuda_neta_sobre_ebitda": _div(v["deuda_neta"], ebitda_anual),
        "margen_ebitda": _div(v["ebitda"], v["ingresos"]),
        "margen_ebit": _div(v["ebit"], v["ingresos"]),
        "margen_neto": _div(v["utilidad_neta"], v["ingresos"]),
        "roa_periodo": _div(v["utilidad_neta"], v["activos"]),
        "roe_periodo": _div(v["utilidad_neta"], v["capital"]),
        "deuda_largo_plazo_pct": _div(v["deuda_lp"], v["deuda_total"]),
    }
    return {"periodo": periodo, "cifras": v, "razones": r}


def razones_financieras(processed: Path) -> dict:
    trim, anual = _cargar(processed / "financieros_trimestral.json"), _cargar(processed / "financieros_anual.json")
    per_anual = [p for p in ("2024-12-31", "2025-12-31") if serie(anual, CONCEPTOS["activos"]).get(p) is not None]
    per_trim = [p for p in ("2026-03-31", "2026-06-30", "2026-09-30") if serie(trim, CONCEPTOS["activos"]).get(p) is not None]
    return {
        "unidades": "millones de USD (razones como fracción; 0.15 = 15%)",
        "anual": [razones_periodo(anual, p) for p in per_anual],
        "trimestral": [razones_periodo(trim, p, factor_anual=4) for p in per_trim],
        "fuente": f"Refinitiv, estados financieros (descarga del {trim.get('fecha_archivo')})",
        "estado": "calculado",
        "notas": [
            "Cobertura de intereses = EBIT / gasto por intereses del periodo; en un trimestre con EBIT negativo sale negativa.",
            "En trimestres, ROA y ROE son del periodo (no anualizados) y deuda neta / EBITDA usa el EBITDA del trimestre x 4.",
            "No hay datos del 4T-2025 en el archivo trimestral, por lo que no se calculan cifras de los últimos doce meses.",
            "Entre el 2T y el 3T de 2026 los ingresos y los activos saltan (ingresos 7,814 a 14,575; activos 192,770 a 254,045); "
            "no se investigó el motivo. Revisar las notas de la empresa antes de interpretar las tendencias.",
        ],
    }

# Estado de cada facilidad de Refinitiv según el 10-Q al 30-sep-2026 (nota 9). clave: (prestatario, tipo, vencimiento)
ESTADO_FAC_10Q = {
    ("Twitter Inc", "Revolver/Line >= 1 Yr.", "2027-10-28"): ("cerrada", "El 10-Q indica que el compromiso se redujo a 0 en feb-2025; ya no existe."),
    ("Twitter Inc", "Term Loan B", "2029-10-28"): ("pagada", "X B-1 Term Loan: pagado el 2-mar-2026 con el bridge (incluye penalización de 425 M junto con el B-3)."),
    ("Twitter Inc", "Term Loan B", "2029-10-27"): ("pagada", "X B-3 Term Loan: pagado el 2-mar-2026 con el bridge."),
    ("xAI Corp", "Term Loan", "2030-06-30"): ("pagada", "xAI Fixed Rate Term Loan: pagado el 2-mar-2026 (penalización de 221 M junto con el flotante)."),
    ("xAI Corp", "Term Loan B", "2030-06-30"): ("pagada", "xAI Floating Rate Term Loan: pagado el 2-mar-2026."),
    ("xAI Corp", "Other Loan", None): ("sin_confirmar", "No se identifica en la nota 9 del 10-Q; podría estar dentro de «otros financiamientos»."),
    ("Space Exploration Technologies Corp", "Bridge Loan", "2027-03-01"): ("pagada", "SpaceX Bridge Loan: pagado en su totalidad en jun-2026 con los SpaceX Notes."),
    ("Space Exploration Technologies Corp", "Revolver/Line >= 1 Yr.", "2028-06-23"): ("sin_confirmar", "El 10-Q solo describe la línea de feb-2025, ampliada a 5,000 M en may-2026; esta de 1,500 M probablemente es la anterior."),
    ("Space Exploration Technologies Corp", "Revolver/Line >= 1 Yr.", "2031-05-19"): ("vigente", "SpaceX Credit Facility ampliada; sin disposiciones en los nueve meses de 2026."),
}
# Nota 9 del 10-Q (30-sep-2026), M USD
NOTA9_10Q = {
    "fecha": "2026-09-30",
    "deuda": [("SpaceX Notes", 25000, 145, 24855), ("X 2027 y X 2030 Notes", 27, 0, 27), ("Otros financiamientos (1)", 12979, 0, 12979)],
    "total_deuda": (38006, 145, 37861), "arrendamientos_financieros": 983, "total_con_arrendamientos": (38989, 145, 38844),
    "corto_plazo": 2698, "largo_plazo": 36146,
    "deuda_2025": {"total_deuda": 22049, "total_con_arrendamientos": 23286},
    "vencimientos": [("2026 (3 meses restantes)", 495), ("2027", 2425), ("2028", 2867), ("2029", 3422), ("2030", 3597), ("Después de 2030", 25200)],
    "spacex_notes": {"cupon_min": 5.35, "cupon_max": 6.65, "cupon_ponderado": 5.855, "tasa_efectiva": 6.072, "plazo_ponderado_anios": 11.7,
                     "valor_razonable": 22932, "valor_en_libros": 24855},
    "otros_financiamientos": {"tasa_fija_ponderada_pct": 6.3, "venta_con_arrendamiento_fallida_cp": 2181, "venta_con_arrendamiento_fallida_lp": 10716},
    "pagos_2026": [("X B-1 y X B-3 Term Loans", "2-mar-2026"), ("xAI Fixed y Floating Term Loans", "2-mar-2026"), ("xAI 12.5 % Senior Secured Notes", "5-mar-2026"),
                   ("SpaceX Bridge Loan (20,000 M)", "jun-2026")],
    "perdida_extincion_bridge_musd": 1526,
}
RIESGO_MERCADO = {
    "fuente": "Prospecto de la salida a bolsa, MD&A «Quantitative and Qualitative Disclosures About Market Risk» (cifras al 31-mar-2026) y 10-Q al 30-sep-2026, punto 3",
    "moneda": ["Los negocios de Connectivity y AI operan en muchos países y en varias monedas; en general, SpaceX es receptor neto de monedas distintas al dólar en sus subsidiarias extranjeras.",
               "No cubre el riesgo cambiario. Un movimiento adverso de 10 % en todas las monedas habría dado una ganancia o pérdida inmaterial al 31-mar-2026 y al 31-dic-2025."],
    "tasa": ["La exposición a tasas viene de su portafolio de inversión, el ingreso por intereses de la caja y sus créditos. Un movimiento de 100 pb en las tasas tendría un efecto inmaterial en el ingreso por intereses.",
             "Al 31-mar-2026 el bridge loan de 20,000 M tenía tasa efectiva de 4.58 %; un alza de 100 pb habría subido el gasto anual por intereses en unos 200 M.",
             "Al 30-sep-2026 el bridge ya estaba pagado y no había deuda a tasa variable (10-Q): el riesgo de tasa del gasto financiero desapareció al refinanciar con bonos fijos."],
    "derivados": "Las notas de los estados auditados (2025 y 1T-2026) y el 10-Q no registran instrumentos derivados: ni coberturas de tasa ni de tipo de cambio. La única mención de «derivatives» es el nombre del ajuste ISDA de una línea de crédito.",
}


def _conciliar(bonos: dict, tot, cp, lp) -> dict:
    """Contrasta Refinitiv contra la nota 9 del 10-Q (30-sep-2026)."""
    sx = [b for b in bonos["bonos"] if b["emisor"].startswith("SPACE EXPLORATION") and b["monto_vigente_usd"]]
    principal = sum(b["monto_vigente_usd"] for b in sx) / 1e6
    cup = sum(b["monto_vigente_usd"] * b["cupon_pct"] for b in sx) / 1e6 / principal if principal else None
    n9 = NOTA9_10Q
    return {"spacex_notes_refinitiv": principal, "spacex_notes_10q": n9["deuda"][0][1], "cupon_ponderado_refinitiv": cup,
            "cupon_ponderado_10q": n9["spacex_notes"]["cupon_ponderado"], "deuda_total_refinitiv": tot, "deuda_total_10q": n9["total_con_arrendamientos"][2],
            "cp_refinitiv": cp, "cp_10q": n9["corto_plazo"], "lp_refinitiv": lp, "lp_10q": n9["largo_plazo"],
            "vencimientos_suman": sum(v for _, v in n9["vencimientos"]), "n_tramos_refinitiv": len(sx)}


def estructura_deuda(processed: Path) -> dict:
    trim = _cargar(processed / "financieros_trimestral.json")
    cal = _cargar(processed / "calendario_vencimientos.json")
    bonos = _cargar(processed / "bonos.json")
    prest = _cargar(processed / "prestamos.json")
    periodo = "2026-09-30"
    cp, lp, tot = (serie(trim, CONCEPTOS[k]).get(periodo) for k in ("deuda_cp", "deuda_lp", "deuda_total"))

    def _est(f):
        return ESTADO_FAC_10Q.get((f["prestatario"], f["tipo"], f.get("vencimiento")), ("sin_confirmar", ""))[0]

    vig = [f for f in prest["facilidades"] if _est(f) == "vigente"]
    anios = sorted(set(cal["pagos_por_anio_usd"]) | {f["vencimiento"][:4] for f in vig if f.get("vencimiento")})
    muro = []
    for a in anios:
        p = cal["pagos_por_anio_usd"].get(a, {})
        fac = sum(f["monto_facilidad_usd"] for f in vig if (f.get("vencimiento") or "")[:4] == a and f["monto_facilidad_usd"])
        muro.append({"anio": int(a), "cupones_musd": p.get("Coupon", 0.0) / 1e6, "principal_bonos_musd": p.get("Principal", 0.0) / 1e6,
                     "facilidades_musd": fac / 1e6})
    vigente = sum(b["monto_vigente_usd"] for b in bonos["bonos"] if b["monto_vigente_usd"]) / 1e6
    return {
        "periodo": periodo,
        "balance": {"deuda_total": tot, "deuda_corto_plazo": cp, "deuda_largo_plazo": lp,
                    "largo_plazo_pct": (lp / tot) if (lp is not None and tot) else None,
                    "cuadra": (cp + lp == tot) if None not in (cp, lp, tot) else None,
                    "fuente": "Refinitiv, balance trimestral", "estado": "dato"},
        "bonos": [{"descripcion": b["descripcion"], "emisor": b["emisor"], "vencimiento": b["vencimiento"], "cupon_pct": b["cupon_pct"],
                   "vigente_musd": (b["monto_vigente_usd"] or 0) / 1e6, "emitido_musd": (b["monto_emitido_usd"] or 0) / 1e6,
                   "precio": b["precio_ultimo"], "yield_pct": b["yield_pct"]} for b in bonos["bonos"]],
        "bonos_vigentes_total_musd": vigente,
        "facilidades": [{"prestatario": f["prestatario"], "tipo": f["tipo"], "vencimiento": f["vencimiento"],
                         "monto_musd": (f["monto_facilidad_usd"] or 0) / 1e6, "estado_10q": _est(f),
                         "detalle_10q": ESTADO_FAC_10Q.get((f["prestatario"], f["tipo"], f.get("vencimiento")), ("", ""))[1]} for f in prest["facilidades"]]
                        + [{"prestatario": "xAI (subsidiaria)", "tipo": "Revolver (10-Q)", "vencimiento": None, "monto_musd": 250.0, "estado_10q": "vigente",
                            "detalle_10q": "Solo aparece en el 10-Q (no en Refinitiv); sin disposiciones en 2026."}],
        "nota9_10q": {**NOTA9_10Q, "conciliacion": _conciliar(bonos, tot, cp, lp)},
        "riesgo_mercado": RIESGO_MERCADO,
        "muro_vencimientos": muro,
        "notas": [
            f"Los bonos vigentes suman {vigente:,.0f} M, menos que la deuda total del balance; el resto son préstamos y otras obligaciones.",
            "Refinitiv lista las facilidades con su monto original y no indica si siguen vigentes. Contrastadas con la nota 9 del 10-Q: el bridge de 20,000 M, los term loans de X y xAI y las notas de xAI al 12.5 % ya fueron pagados en 2026, así que el muro de vencimientos solo cuenta las facilidades vigentes (la de 5,000 M, sin saldo dispuesto).",
            "Dos facilidades de Refinitiv no se pueden confirmar en el 10-Q (un préstamo de xAI por 3,400 M sin fecha y una línea de SpaceX por 1,500 M al 2028); se muestran marcadas y fuera del muro.",
            "Los bonos de 2027 y 2030 figuran emitidos por X Corp. (empresa adquirida): su monto vigente es muy pequeño frente a lo emitido.",
            "Los cupones son los pagos anuales de los bonos vigentes; el calendario excluye préstamos.",
        ],
        "fuente": "Refinitiv: balance, bonos, calendario de vencimientos y prestamos",
        "estado": "dato / calculado",
    }


def comparables(processed: Path) -> dict:
    peers = _cargar(processed / "peers.json")
    pb = {e["Identifier (RIC)"]: e for e in _cargar(processed / "peers_balance.json")["empresas"]}
    vols = _cargar(processed / "resumen_mercado.json")["volatilidad_realizada"]["valor"]
    cols = {"cap": "Market Cap (usd)", "pe": "P/E(Time Series Ratio)", "roe": "Return on Average Common Equity - %, TTM (FI0)",
            "d_k": "Total Debt Percentage of Total Equity (FY0)", "margen": "Income after Tax Margin - % (FY0)",
            "beta": "Beta 5 Year", "nd_ebitda": "Net Debt / EBITDA (SmartEstimate ®) (FY1)",
            "ev_ebitda": "Enterprise Value to EBITDA (FY0)", "crec": "Revenue 5 YR Hist Growth", "dy": "Curr Dividend Yield - Common - Net - Issue - %, Annized"}
    filas = []
    for e in peers["empresas"]:
        ric = e["Identifier (RIC)"]
        t = ric.split(".")[0]
        extra = pb.get(ric, {})
        vol = vols.get(t.lower(), {}).get("vol_realizada_total") if t.lower() in vols else None
        filas.append({
            "ticker": t, "nombre": e["Company Name"], "cap_musd": (e.get(cols["cap"]) or 0) / 1e6 if e.get(cols["cap"]) else None,
            "pe": e.get(cols["pe"]), "roe": e.get(cols["roe"]), "deuda_capital": e.get(cols["d_k"]), "margen_neto": e.get(cols["margen"]),
            "beta_5a": e.get(cols["beta"]), "deuda_neta_ebitda_fy1": e.get(cols["nd_ebitda"]), "ev_ebitda": e.get(cols["ev_ebitda"]),
            "crecimiento_ingresos_5a_pct": e.get(cols["crec"]), "rendimiento_dividendo": e.get(cols["dy"]),
            "razon_circulante": extra.get("Current Ratio (FI0)"), "ebitda_sobre_intereses": extra.get("Credit SmartRatios EBITDA / Interest Expense, TTM"),
            "calificacion_emisor": extra.get("Issuer Rating"), "vol_realizada": vol, "es_spcx": t == "SPCX",
        })
    return {
        "filas": filas,
        "columnas": {"deuda_capital": "Deuda / capital (FY0)", "roe": "ROE (TTM)", "margen_neto": "Margen neto (FY0)",
                     "deuda_neta_ebitda_fy1": "Deuda neta / EBITDA (FY1, estimado)", "ev_ebitda": "EV / EBITDA (FY0)",
                     "crecimiento_ingresos_5a_pct": "Crec. ingresos 5 años (%)"},
        "notas": [
            "Cada columna usa su propio periodo (FY0, FY1, TTM); no son estrictamente comparables entre sí.",
            "'—' = Refinitiv no devolvio el dato (por ejemplo, SPCX no tiene ROE ni beta por su historia corta).",
            "El ROE de BA (≈150%) y su deuda/capital (≈991%) salen distorsionados por un capital contable casi nulo.",
            "La volatilidad realizada de los comparables es de 2 años de datos; la de SPCX, de 94 días.",
            "La calificación de SPCX en Refinitiv (Baa1) coincide con la de Moody's; NR = sin calificación..",
        ],
        "fuente": peers["fuente"], "fecha_archivo": peers["fecha_archivo"], "estado": "dato",
    }


def construir(processed: Path) -> dict:
    return {"razones": razones_financieras(processed), "deuda": estructura_deuda(processed), "comparables": comparables(processed)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--docs", default="docs/data")
    a = ap.parse_args(argv)
    processed, docs = Path(a.processed), Path(a.docs)
    out = construir(processed)
    (processed / "analisis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(processed / "analisis.json", docs / "analisis.json")
    u = out["razones"]["trimestral"][-1]
    print(f"{u['periodo']}: deuda/activos {u['razones']['deuda_sobre_activos']:.3f} | margen EBITDA {u['razones']['margen_ebitda']:.3f} | "
          f"{len(out['deuda']['muro_vencimientos'])} años en el muro | {len(out['comparables']['filas'])} comparables")
    print(f"Listo. {processed / 'analisis.json'} y copia en {docs}")


if __name__ == "__main__":
    main()
