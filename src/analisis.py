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


def estructura_deuda(processed: Path) -> dict:
    trim = _cargar(processed / "financieros_trimestral.json")
    cal = _cargar(processed / "calendario_vencimientos.json")
    bonos = _cargar(processed / "bonos.json")
    prest = _cargar(processed / "prestamos.json")
    periodo = "2026-09-30"
    cp, lp, tot = (serie(trim, CONCEPTOS[k]).get(periodo) for k in ("deuda_cp", "deuda_lp", "deuda_total"))

    anios = sorted(set(cal["pagos_por_anio_usd"]) | {f["vencimiento"][:4] for f in prest["facilidades"] if f.get("vencimiento")})
    muro = []
    for a in anios:
        p = cal["pagos_por_anio_usd"].get(a, {})
        fac = sum(f["monto_facilidad_usd"] for f in prest["facilidades"] if (f.get("vencimiento") or "")[:4] == a and f["monto_facilidad_usd"])
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
                         "monto_musd": (f["monto_facilidad_usd"] or 0) / 1e6} for f in prest["facilidades"]],
        "muro_vencimientos": muro,
        "notas": [
            f"Los bonos vigentes suman {vigente:,.0f} M, menos que la deuda total del balance; el resto son préstamos y otras obligaciones.",
            "Las facilidades de crédito muestran el monto de la facilidad, no el saldo dispuesto; Refinitiv no indica cuánto está usado. "
            "La facilidad puente de 20,000 M (vence 2027) podría estar ya repagada; no se verificó.",
            "Una facilidad sin fecha de vencimiento (3,400 M) no aparece en el muro de vencimientos.",
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
