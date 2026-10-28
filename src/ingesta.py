"""Convierte los exportes de Refinitiv (data/raw/*.xlsx) en JSON (data/processed/*.json).

Uso, desde la raiz del repo:
    python -m src.ingesta
    python -m src.ingesta --raw data/raw --out data/processed --fecha 2026-10-26

Reglas:
  - Los archivos se llaman AAAA-MM-DD_tema.xlsx. Por cada tema se usa el de fecha mas reciente.
  - Los exportes originales no se modifican.
  - Todo valor numerico sale con etiqueta: fuente, fecha y estado (dato / calculado).
  - Un 0 en precio o yield significa "sin dato" en estos exportes y se guarda como null.
  - Si falta un archivo, se avisa y se sigue con los demas.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PATRON_ARCHIVO = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.xlsx$")
COMPARABLES = ["rklb", "ktos", "avav", "ba", "noc"]


# --------------------------------------------------------------------------- utilidades
def _num(x):
    """Numero o None. Cadenas como '--' o 'NA' pasan a None."""
    if x is None:
        return None
    if isinstance(x, str):
        s = x.replace(",", "").strip()
        if s in ("", "--", "NA", "NaN", "nan"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _cero_a_none(x):
    v = _num(x)
    return None if v is None or v == 0 else v


def _fecha_iso(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(x).date().isoformat()
    try:
        t = pd.to_datetime(x, errors="coerce")
    except Exception:
        return None
    return None if pd.isna(t) else t.date().isoformat()


def _limpio(obj):
    """Deja el objeto listo para JSON: NaN -> None, fechas -> texto, numpy -> python."""
    if isinstance(obj, dict):
        return {str(k): _limpio(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpio(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(obj).date().isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if obj is pd.NaT:
        return None
    return obj


def etiqueta(valor, fuente, fecha, estado="dato", nota=None):
    d = {"valor": valor, "fuente": fuente, "fecha": fecha, "estado": estado}
    if nota:
        d["nota"] = nota
    return d


def leer_hojas(ruta: Path) -> dict[str, pd.DataFrame]:
    """Lee todas las hojas sin encabezado. Corrige exportes con atributos 'NaN' que rompen openpyxl."""
    try:
        return pd.read_excel(ruta, sheet_name=None, header=None)
    except TypeError:
        tmp = ruta.with_suffix(".reparado.xlsx")
        try:
            with zipfile.ZipFile(ruta) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for it in zin.infolist():
                    data = zin.read(it.filename)
                    if it.filename.startswith("xl/worksheets/"):
                        data = re.sub(rb'\s(outlineLevel|collapsed)="NaN"', b"", data)
                    zout.writestr(it, data)
            return pd.read_excel(tmp, sheet_name=None, header=None)
        finally:
            tmp.unlink(missing_ok=True)


def _primera_hoja(ruta: Path) -> pd.DataFrame:
    hojas = leer_hojas(ruta)
    return hojas[next(iter(hojas))]


def buscar_archivos(raw: Path) -> dict[str, tuple[str, Path]]:
    """Devuelve {tema: (fecha, ruta)} con el archivo mas reciente de cada tema."""
    out: dict[str, tuple[str, Path]] = {}
    for p in sorted(Path(raw).glob("*.xlsx")):
        m = PATRON_ARCHIVO.match(p.name)
        if not m:
            continue
        fecha, tema = m.groups()
        if tema not in out or fecha > out[tema][0]:
            out[tema] = (fecha, p)
    return out


def _fila_con(df: pd.DataFrame, texto: str, col: int = 0) -> int:
    idx = df.index[df[col].astype(str).str.strip() == texto]
    if len(idx) == 0:
        raise ValueError(f"No encontre la fila '{texto}' en la columna {col}")
    return int(idx[0])


# --------------------------------------------------------------------------- precios
def leer_precios(ruta: Path) -> dict:
    """Precio historico diario. El encabezado cambia de fila entre archivos, se busca 'Exchange Date'."""
    df = _primera_hoja(ruta)
    h = _fila_con(df, "Exchange Date")
    cols = [c if isinstance(c, str) else None for c in df.iloc[h].tolist()]
    cuerpo = df.iloc[h + 1:].copy()
    cuerpo.columns = range(cuerpo.shape[1])
    cuerpo = cuerpo.loc[:, [i for i, c in enumerate(cols) if c]]
    cuerpo.columns = [c for c in cols if c]
    cuerpo["Exchange Date"] = pd.to_datetime(cuerpo["Exchange Date"], errors="coerce")
    cuerpo = cuerpo.dropna(subset=["Exchange Date"]).sort_values("Exchange Date")
    periodo = next((m for m in (re.match(r"History Period:\s*(.+)", str(v)) for v in df.iloc[:h, 0].dropna()) if m), None)
    registros = [
        {
            "fecha": r["Exchange Date"].date().isoformat(),
            "cierre": _num(r["Close"]),
            "apertura": _num(r.get("Open")),
            "minimo": _num(r.get("Low")),
            "maximo": _num(r.get("High")),
            "volumen": _num(r.get("Volume")),
            "monto_usd": _num(r.get("Turnover - USD")),
        }
        for _, r in cuerpo.iterrows()
    ]
    ticker = str(df.iloc[3, 0]) if h > 3 else None
    return {
        "ticker": ticker,
        "historia_declarada": periodo.group(1).strip() if periodo else None,
        "desde": registros[0]["fecha"] if registros else None,
        "hasta": registros[-1]["fecha"] if registros else None,
        "n_dias": len(registros),
        "datos": registros,
    }


def volatilidad_realizada(cierres: list[float], dias_anio: int = 252) -> float | None:
    """Desviacion estandar anualizada de los rendimientos logaritmicos diarios (en fraccion, 0.80 = 80%)."""
    c = np.array([x for x in cierres if x is not None and x > 0], dtype=float)
    if len(c) < 3:
        return None
    r = np.diff(np.log(c))
    return float(r.std(ddof=1) * math.sqrt(dias_anio))


# --------------------------------------------------------------------------- treasuries
def _plazo_en_anios(s: str) -> float | None:
    s = str(s).strip().upper()
    m = re.fullmatch(r"(\d+)M(?:(\d+)D)?", s)
    if m:
        return int(m.group(1)) / 12 + (int(m.group(2)) / 365.25 if m.group(2) else 0)
    m = re.fullmatch(r"(\d+)Y", s)
    return float(m.group(1)) if m else None


def leer_treasuries(ruta: Path) -> dict:
    df = _primera_hoja(ruta)
    h = _fila_con(df, "Maturity")
    filas = []
    for _, r in df.iloc[h + 1:].iterrows():
        t, y = _plazo_en_anios(r[0]), _num(r[1])
        if t is not None and y is not None:
            filas.append({"plazo": str(r[0]).strip(), "anios": t, "yield_pct": y})
    return {"descripcion": str(df.iloc[h, 1]), "puntos": sorted(filas, key=lambda x: x["anios"])}


def interpolar(puntos_x: list[float], puntos_y: list[float], x: float) -> float:
    """Interpolacion lineal. Fuera del rango se queda en el extremo (no extrapola)."""
    return float(np.interp(x, puntos_x, puntos_y))


# --------------------------------------------------------------------------- bonos y prestamos
def leer_bonos(ruta: Path, fecha_valuacion: str) -> dict:
    hojas = leer_hojas(ruta)

    def tabla(nombre):
        df = hojas[nombre]
        h = _fila_con(df, "Description")
        t = df.iloc[h + 1:].copy()
        t.columns = [str(c) for c in df.iloc[h].tolist()]
        return t.dropna(subset=["Description"])

    hoy = pd.Timestamp(fecha_valuacion)

    def a_registro(r):
        venc = pd.to_datetime(r["Maturity Date"], errors="coerce")
        return {
            "descripcion": re.sub(r"\s+", " ", str(r["Description"])).strip(),
            "isin": r["ISIN"],
            "ric": r["RIC"],
            "vencimiento": venc.date().isoformat() if pd.notna(venc) else None,
            "plazo_anios": float((venc - hoy).days / 365.25) if pd.notna(venc) else None,
            "cupon_pct": _num(r["Coupon"]),
            "monto_vigente_usd": _num(r["Amount Outstanding"]),
            "monto_emitido_usd": _num(r["Issued Amount"]),
            "precio_ultimo": _cero_a_none(r["Last Price"]),
            "yield_pct": _cero_a_none(r["Yield"]),
            "tipo_yield": None if str(r["Yield Type"]).strip() in ("--", "nan") else r["Yield Type"],
            "oas_pb": _cero_a_none(r["Option Adjusted Spread"]),
            "duracion_modificada": _cero_a_none(r["Modified Duration"]),
            "prelacion": r["Rank (Seniority)"],
            "convertible": str(r["Is Convertible"]).strip().upper() == "Y",
            "colocacion": r["Offering Type"],
            "emisor": r["Issuer"],
            "estatus": r["Asset Status"],
            "fecha_emision": _fecha_iso(r["Issue Date"]),
        }

    vigentes = tabla("Bonds")
    regs = vigentes["Asset Duplicated"].astype(str).str.strip().eq("RGSRS")
    unicos = [a_registro(r) for _, r in vigentes[~regs].iterrows()]

    inactivos = []
    if "Inactive Bonds" in hojas:
        for _, r in tabla("Inactive Bonds").iterrows():
            if str(r["Asset Duplicated"]).strip() == "CRSRB":
                continue  # copia duplicada del mismo bono
            venc = pd.to_datetime(r["Maturity Date"], errors="coerce")
            inactivos.append({
                "descripcion": re.sub(r"\s+", " ", str(r["Description"])).strip(),
                "vencimiento": venc.date().isoformat() if pd.notna(venc) else None,
                "cupon_clase": r["Coupon Class"],
                "monto_emitido_usd": _num(r["Issued Amount"]),
                "estatus": r["Asset Status"],
                "emisor": r["Issuer"],
                "prelacion": r["Rank (Seniority)"],
            })
    return {
        "filas_en_exporte": int(len(vigentes)),
        "bonos_unicos": len(unicos),
        "nota": "Cada bono sale dos veces en Refinitiv (144A y Reg S, con distinto ISIN). "
                "Se conserva la fila 144A y se descarta la marcada RGSRS para no duplicar la deuda.",
        "bonos": unicos,
        "inactivos": inactivos,
    }


def leer_prestamos(ruta: Path) -> dict:
    df = leer_hojas(ruta)["Loans"]
    facilidades, bloque, columnas = [], None, None
    for _, r in df.iterrows():
        c0 = str(r[0]).strip()
        if c0 in ("Loans", "Issue Date", "nan"):
            continue
        if c0 == "Total":
            break
        if c0 == "Facility Type":
            columnas = [str(c) for c in r.tolist()]
            continue
        if pd.isna(r[4]):  # encabezado de bloque: "28-Oct-2022 Twitter Inc | proposito | monto | n"
            m = re.match(r"(\d{2}-\w{3}-\d{4})\s+(.*)", c0)
            bloque = {
                "fecha": _fecha_iso(m.group(1)) if m else None,
                "prestatario": m.group(2) if m else c0,
                "proposito": r[1],
                "monto_bloque_usd": _num(r[2]),
            }
            continue
        if columnas is None or bloque is None:
            continue
        v = dict(zip(columnas, r.tolist()))
        facilidades.append({
            **bloque,
            "tipo": v.get("Facility Type"),
            "vencimiento": _fecha_iso(v.get("Maturity Date")),
            "monto_facilidad_usd": _num(v.get("Facility Amount")),
            "tasa_base_spread": None if str(v.get("Base Rate/Spd")).strip() in ("--", "nan") else v.get("Base Rate/Spd"),
            "precio_mid_pct": _cero_a_none(v.get("Mid Price (%)")),
            "yield_pct": _cero_a_none(v.get("Yield (%)")),
        })
    return {
        "nota": "monto_facilidad_usd es el tamano de la facilidad, no el saldo dispuesto. "
                "El exporte no trae saldo vigente de los prestamos.",
        "facilidades": facilidades,
    }


def leer_calendario(ruta: Path) -> dict:
    df = _primera_hoja(ruta)
    h = _fila_con(df, "Date")
    t = df.iloc[h + 1:].copy()
    t.columns = [str(c) for c in df.iloc[h].tolist()]
    t = t.dropna(subset=["Date"])
    # cada fecha se interpreta por separado: pandas fija el formato con la primera fila y las demas quedarian vacias
    t["_f"] = t["Date"].map(lambda v: pd.to_datetime(v, errors="coerce"))
    t["_m"] = t["Amount Outstanding, USD"].map(_num)
    t["_desc"] = t["Description"].astype(str).str.strip()
    # cada pago sale dos veces (dos ISIN del mismo bono): se deduplica por fecha, evento y descripcion
    t = t.dropna(subset=["_f"]).drop_duplicates(subset=["_f", "Event", "_desc"])
    eventos = [
        {"fecha": r["_f"].date().isoformat(), "evento": r["Event"], "bono": r["_desc"], "monto_usd": r["_m"]}
        for _, r in t.sort_values(["_f", "Event"]).iterrows()
    ]
    anual: dict[str, dict[str, float]] = {}
    for e in eventos:
        a = anual.setdefault(e["fecha"][:4], {"Coupon": 0.0, "Principal": 0.0})
        if e["evento"] in a and e["monto_usd"] is not None:
            a[e["evento"]] += e["monto_usd"]
    return {
        "nota": "Solo incluye bonos (no prestamos). 'Call' marca la fecha desde la que el bono puede rescatarse; "
                "no es un pago y no se suma a los totales. 'monto_usd' es el monto del evento, no el saldo.",
        "eventos": eventos,
        "pagos_por_anio_usd": {k: v for k, v in sorted(anual.items())},
    }


# --------------------------------------------------------------------------- peers
def leer_peers(ruta: Path) -> dict:
    df = _primera_hoja(ruta)
    nombres, vistos = [], {}
    for c in df.iloc[0].tolist():
        c = re.sub(r"\s+", " ", str(c)).strip()
        vistos[c] = vistos.get(c, 0) + 1
        nombres.append(c if vistos[c] == 1 else f"{c} [{vistos[c]}]")
    filas = []
    for _, r in df.iloc[1:].iterrows():
        d = {n: (_num(v) if i >= 2 and n != "Issuer Rating" else v) for i, (n, v) in enumerate(zip(nombres, r.tolist()))}
        filas.append({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()})
    return {
        "nota": "Cada columna usa un periodo distinto (FY0, FY1, FI0, TTM), indicado entre parentesis en su nombre; "
                "no son comparables entre si sin revisar el periodo. Las razones vienen como fraccion (0.55 = 55%). "
                "Si dos columnas tuvieran el mismo nombre, la segunda lleva el sufijo [2].",
        "columnas": nombres,
        "empresas": filas,
    }


# --------------------------------------------------------------------------- financieros
def leer_estado(df: pd.DataFrame) -> dict:
    """Una hoja de Company Fundamentals: filas = conceptos, columnas = periodos."""
    col_etiqueta = next(c for c in range(min(3, df.shape[1])) if (df[c].astype(str).str.strip() == "Period End Date").any())
    h = _fila_con(df, "Period End Date", col_etiqueta)
    periodos = {c: _fecha_iso(df.iloc[h, c]) for c in range(col_etiqueta + 1, df.shape[1]) if _fecha_iso(df.iloc[h, c])}
    export = next((df.iloc[i, col_etiqueta + 1] for i in range(h) if str(df.iloc[i, col_etiqueta]).strip() == "Export Date"), None)
    seccion, conceptos = None, []
    for i in range(h + 1, df.shape[0]):
        etiqueta_fila = df.iloc[i, col_etiqueta]
        if pd.isna(etiqueta_fila):
            continue
        etiqueta_fila = re.sub(r"\s+", " ", str(etiqueta_fila)).strip()
        if etiqueta_fila in ("Standardized Currency", "Template Type", "Statement Date"):
            continue
        valores = {p: _num(df.iloc[i, c]) for c, p in periodos.items()}
        if all(v is None for v in valores.values()):
            seccion = etiqueta_fila  # fila de encabezado de seccion
            continue
        conceptos.append({"seccion": seccion, "concepto": etiqueta_fila, "valores": valores})
    return {
        "exportado": _fecha_iso(export),
        "periodos": sorted(periodos.values()),
        "conceptos": conceptos,
    }


def leer_financieros(ruta: Path) -> dict:
    return {hoja: leer_estado(df) for hoja, df in leer_hojas(ruta).items()}


def concepto(estado: dict, nombre: str, ultimo_con_dato: bool = True) -> tuple[str | None, float | None]:
    """Busca un concepto por nombre exacto y devuelve (periodo, valor) del ultimo periodo con dato."""
    for c in estado["conceptos"]:
        if c["concepto"] == nombre:
            for p in sorted(c["valores"], reverse=True):
                if c["valores"][p] is not None:
                    return p, c["valores"][p]
    return None, None


# --------------------------------------------------------------------------- construccion
def construir(raw: Path, out: Path, fecha_valuacion: str | None = None) -> dict:
    raw, out = Path(raw), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    archivos = buscar_archivos(raw)
    avisos: list[str] = []

    def f(tema):
        if tema not in archivos:
            avisos.append(f"Falta el archivo de '{tema}' en {raw}")
            return None, None
        return archivos[tema]

    def guardar(nombre, contenido):
        (out / nombre).write_text(json.dumps(_limpio(contenido), ensure_ascii=False, indent=1), encoding="utf-8")

    fecha_bonos, p_bonos = f("bonos")
    fecha_val = fecha_valuacion or fecha_bonos or max((a[0] for a in archivos.values()), default=date.today().isoformat())
    resumen: dict = {"fecha_valuacion": fecha_val, "generado_desde": {t: a[1].name for t, a in sorted(archivos.items())}}

    # precios
    precios = {}
    for tk in ["spcx"] + COMPARABLES:
        fecha, p = f(f"precios_{tk}")
        if p:
            d = leer_precios(p)
            d.update({"fuente": "Refinitiv, " + p.name, "fecha_archivo": fecha})
            precios[tk] = d
            guardar(f"precios_{tk}.json", d)
    if precios:
        vols = {}
        for tk, d in precios.items():
            cierres = [x["cierre"] for x in d["datos"]]
            vols[tk] = {
                "vol_realizada_total": volatilidad_realizada(cierres),
                "vol_realizada_60d": volatilidad_realizada(cierres[-61:]),
                "n_dias": d["n_dias"], "desde": d["desde"], "hasta": d["hasta"],
                "historia_declarada": d["historia_declarada"], "fecha_archivo": d["fecha_archivo"],
            }
        resumen["volatilidad_realizada"] = etiqueta(
            vols, "calculado de precios historicos (Refinitiv)", fecha_val, "calculado",
            "Desv. estandar anualizada (x raiz de 252) de rendimientos log diarios. Fraccion: 0.80 = 80%. "
            "Con poca historia es poco confiable; revisar n_dias y desde.")
        if "spcx" in precios and precios["spcx"]["datos"]:
            u = precios["spcx"]["datos"][-1]
            resumen["precio_referencia_spcx"] = etiqueta(u["cierre"], "Refinitiv, " + archivos["precios_spcx"][1].name, u["fecha"],
                                                         "dato", "Ultimo cierre disponible en el exporte.")

    # treasuries
    fecha_t, p_t = f("treasuries")
    curva = None
    if p_t:
        curva = leer_treasuries(p_t)
        curva.update({"fuente": "Refinitiv, " + p_t.name, "fecha_archivo": fecha_t,
                      "nota": "Yield bid en tiempo real al momento de la descarga; el archivo no trae hora."})
        guardar("treasuries.json", curva)
        xs = [p["anios"] for p in curva["puntos"]]
        ys = [p["yield_pct"] for p in curva["puntos"]]
        resumen["ust_6y_pct"] = etiqueta(interpolar(xs, ys, 6.0), "interpolacion lineal 5Y-7Y, Refinitiv " + p_t.name, fecha_t,
                                         "calculado", "Tasa libre de riesgo a 6 anios.")

    # bonos / prestamos
    if p_bonos:
        b = leer_bonos(p_bonos, fecha_val)
        b.update({"fuente": "Refinitiv, " + p_bonos.name, "fecha_archivo": fecha_bonos})
        guardar("bonos.json", b)
        guardar("prestamos.json", {**leer_prestamos(p_bonos), "fuente": "Refinitiv, " + p_bonos.name, "fecha_archivo": fecha_bonos})
        curva_b = [x for x in b["bonos"] if x["yield_pct"] and x["monto_vigente_usd"] and x["monto_vigente_usd"] >= 1e9 and x["plazo_anios"] and x["plazo_anios"] > 0]
        curva_b.sort(key=lambda x: x["plazo_anios"])
        if len(curva_b) >= 2:
            t = [x["plazo_anios"] for x in curva_b]
            y6 = interpolar(t, [x["yield_pct"] for x in curva_b], 6.0)
            o6 = interpolar(t, [x["oas_pb"] for x in curva_b if x["oas_pb"]], 6.0) if all(x["oas_pb"] for x in curva_b) else None
            resumen["yield_bonos_spcx_6y_pct"] = etiqueta(
                y6, "interpolacion lineal entre bonos SPCX con >= 1,000 millones vigentes, Refinitiv " + p_bonos.name, fecha_bonos, "calculado",
                "Excluye los bonos 2027 y 2030 (saldo residual, sin precio confiable). Candidata a tasa de descuento del bono simple.")
            if o6 is not None:
                resumen["oas_bonos_spcx_6y_pb"] = etiqueta(o6, "interpolacion lineal, Refinitiv " + p_bonos.name, fecha_bonos, "calculado")
            if "ust_6y_pct" in resumen:
                resumen["spread_bonos_vs_ust_6y_pb"] = etiqueta((y6 - resumen["ust_6y_pct"]["valor"]) * 100, "yield bonos SPCX 6Y menos UST 6Y",
                                                                fecha_bonos, "calculado")

    # calendario
    fecha_c, p_c = f("calendario-vencimientos")
    if p_c:
        guardar("calendario_vencimientos.json", {**leer_calendario(p_c), "fuente": "Refinitiv, " + p_c.name, "fecha_archivo": fecha_c})

    # peers
    for tema, salida in (("peers", "peers.json"), ("peers_balance", "peers_balance.json")):
        fecha_p, p_p = f(tema)
        if p_p:
            guardar(salida, {**leer_peers(p_p), "fuente": "Refinitiv, " + p_p.name, "fecha_archivo": fecha_p})

    # financieros
    estados = {}
    for tema, salida in (("financieros_trimestral", "financieros_trimestral.json"),
                         ("financieros_anual", "financieros_anual.json"),
                         ("financieros_as-reported", "financieros_as_reported.json")):
        fecha_f, p_f = f(tema)
        if p_f:
            d = leer_financieros(p_f)
            estados[tema] = d
            guardar(salida, {"fuente": "Refinitiv, " + p_f.name, "fecha_archivo": fecha_f, "unidades": "millones de USD", "hojas": d})
    tri = estados.get("financieros_trimestral", {}).get("Balance Sheet")
    if tri:
        fuente = "Refinitiv, " + archivos["financieros_trimestral"][1].name
        for clave, nombre in (("deuda_total_musd", "Debt - Total"), ("caja_e_inversiones_cp_musd", "Cash & Short-Term Investments"),
                              ("efectivo_musd", "Cash & Cash Equivalents")):
            per, val = concepto(tri, nombre)
            if val is not None:
                resumen[clave] = etiqueta(val, fuente, per, "dato", "Fin de periodo; millones de USD.")
        if "deuda_total_musd" in resumen and "caja_e_inversiones_cp_musd" in resumen:
            resumen["deuda_neta_musd"] = etiqueta(
                resumen["deuda_total_musd"]["valor"] - resumen["caja_e_inversiones_cp_musd"]["valor"], fuente,
                resumen["deuda_total_musd"]["fecha"], "calculado", "Deuda total menos caja e inversiones de corto plazo; negativo = caja neta.")

    resumen["avisos"] = avisos
    guardar("resumen_mercado.json", resumen)
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--out", default=str(RAIZ / "data" / "processed"))
    ap.add_argument("--fecha", default=None, help="Fecha de valuacion AAAA-MM-DD (por omision, la del archivo de bonos)")
    a = ap.parse_args(argv)
    r = construir(Path(a.raw), Path(a.out), a.fecha)
    print(f"Listo. JSON en {a.out}")
    for k, v in r.items():
        if isinstance(v, dict) and isinstance(v.get("valor"), (int, float)):
            print(f"  {k}: {v['valor']:.4f}  ({v['estado']}, {v['fecha']})")
    for aviso in r["avisos"]:
        print("  AVISO:", aviso)


if __name__ == "__main__":
    main()
