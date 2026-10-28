"""Pruebas de src/ingesta.py con archivos sinteticos (no usan datos de Refinitiv)."""
import json
import math
import sys
import zipfile
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import ingesta as ing  # noqa: E402


def crear_xlsx(ruta: Path, hojas: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for fila in filas:
            ws.append(fila)
    wb.save(ruta)
    return ruta


# ------------------------------------------------------------------ utilidades
def test_buscar_archivos_toma_el_mas_reciente(tmp_path):
    for n in ["2026-10-19_bonos.xlsx", "2026-10-26_bonos.xlsx", "2026-10-26_precios_spcx.xlsx", "notas.xlsx", "026-10-26_treasuries.xlsx"]:
        (tmp_path / n).write_bytes(b"x")
    r = ing.buscar_archivos(tmp_path)
    assert r["bonos"][0] == "2026-10-26"
    assert "precios_spcx" in r
    assert "treasuries" not in r  # nombre mal escrito (sin el primer digito del anio) se ignora
    assert "notas" not in r


@pytest.mark.parametrize("texto,esperado", [("1M", 1 / 12), ("6M", 0.5), ("5Y", 5.0), ("30Y", 30.0), ("1M7D", 1 / 12 + 7 / 365.25), ("raro", None)])
def test_plazo_en_anios(texto, esperado):
    r = ing._plazo_en_anios(texto)
    assert (r is None) if esperado is None else r == pytest.approx(esperado)


def test_num_trata_marcadores_como_vacio():
    assert ing._num("--") is None and ing._num("NA") is None and ing._num(float("nan")) is None
    assert ing._num("1,234.5") == 1234.5 and ing._num(7) == 7.0
    assert ing._cero_a_none(0) is None and ing._cero_a_none(3.2) == 3.2


def test_interpolar_seis_anios_es_el_promedio_de_5_y_7():
    assert ing.interpolar([5, 7], [4.8661, 4.9394], 6.0) == pytest.approx((4.8661 + 4.9394) / 2)
    assert ing.interpolar([5, 7], [4.0, 5.0], 10.0) == 5.0  # no extrapola


def test_volatilidad_realizada():
    assert ing.volatilidad_realizada([100.0] * 10) == pytest.approx(0.0)
    assert ing.volatilidad_realizada([100.0, 101.0]) is None  # muy pocos datos
    cierres = [100 * math.exp(0.01 * (-1) ** i * (i % 3)) for i in range(40)]
    import numpy as np
    esperado = np.diff(np.log(cierres)).std(ddof=1) * math.sqrt(252)
    assert ing.volatilidad_realizada(cierres) == pytest.approx(esperado)


def test_leer_hojas_repara_atributo_nan(tmp_path):
    ruta = crear_xlsx(tmp_path / "a.xlsx", {"H": [["a", 1], ["b", 2]]})
    roto = tmp_path / "roto.xlsx"
    with zipfile.ZipFile(ruta) as zin, zipfile.ZipFile(roto, "w") as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename.startswith("xl/worksheets/"):
                data = data.replace(b'<row r="1"', b'<row r="1" outlineLevel="NaN"')
            zout.writestr(it, data)
    assert ing.leer_hojas(roto)["H"].shape == (2, 2)


# ------------------------------------------------------------------ precios
def test_leer_precios_encuentra_encabezado_y_ordena(tmp_path):
    filas = [["Rocket Lab Corp | Price History"], [None], [None], ["RKLB.O"], ["Interval: Daily"], ["History Period: 2 Years"],
             ["Currency Conversion: USD"], ["VAP: Total", 100], ["Price", "Volume"], ["10.00 - 12.00", 5],
             ["Exchange Date", "Close", "Net", "%Chg", "Open", "Low", "High", "Volume", "Turnover - USD"],
             ["2026-10-27", 12.0, 1.0, 0.09, 11.0, 10.5, 12.5, 1000, 12000],
             ["2026-10-26", 11.0, None, None, 10.0, 9.5, 11.5, 900, 9900]]
    d = ing.leer_precios(crear_xlsx(tmp_path / "p.xlsx", {"S": filas}))
    assert d["ticker"] == "RKLB.O" and d["historia_declarada"] == "2 Years"
    assert d["n_dias"] == 2 and d["desde"] == "2026-10-26" and d["hasta"] == "2026-10-27"
    assert d["datos"][0]["cierre"] == 11.0 and d["datos"][1]["volumen"] == 1000


# ------------------------------------------------------------------ treasuries
def test_leer_treasuries(tmp_path):
    filas = [["Consolidated"], ["Maturity", "0#USBMK= Realtime Bid Yield"], ["7Y", 4.9394], ["5Y", 4.8661], ["1M7D", 4.0212]]
    d = ing.leer_treasuries(crear_xlsx(tmp_path / "t.xlsx", {"S": filas}))
    assert [p["plazo"] for p in d["puntos"]] == ["1M7D", "5Y", "7Y"]  # ordenados por plazo
    assert d["puntos"][1]["yield_pct"] == 4.8661


# ------------------------------------------------------------------ bonos y prestamos
COLS_BONOS = ["Description", "Asset Duplicated", "Maturity Date", "Amount Outstanding", "Issued Amount", "Coupon", "Coupon Class",
              "ISIN", "RIC", "Issue Date", "Rank (Seniority)", "Modified Duration", "Option Adjusted Spread", "Yield", "Yield Type",
              "Last Price", "Is Convertible", "Offering Type", "Issuer", "Asset Status"]


def fila_bono(desc, dup, venc, saldo, cupon, precio, yld, oas):
    return [desc, dup, venc, saldo, saldo, cupon, "Fixed Coupon", "US0000", "RIC=", "2026-06-26", "Senior Unsecured", 5.0, oas, yld, "CB",
            precio, "N", "144A", "SPCX", "Issued"]


def test_leer_bonos_quita_duplicados_y_ceros(tmp_path):
    filas = [["Bonds"], ["Total records", "Total"], [4, 1], COLS_BONOS,
             fila_bono("SPCX 5.350 2031", "RGSRS", "2031-07-15", 7e9, 5.35, 93.5, 6.96, 215.0),
             fila_bono("SPCX 5.350 2031", "--", "2031-07-15", 7e9, 5.35, 93.8, 6.90, 208.0),
             fila_bono("SPCX 5.000 2030", "RGSRS", "2030-03-01", 2e6, 5.0, 0, 0, 0),
             fila_bono("SPCX 5.000 2030", "--", "2030-03-01", 2e6, 5.0, 0, 0, 0)]
    b = ing.leer_bonos(crear_xlsx(tmp_path / "b.xlsx", {"Bonds": filas}), "2026-10-26")
    assert b["filas_en_exporte"] == 4 and b["bonos_unicos"] == 2
    b31, b30 = b["bonos"]
    assert b31["yield_pct"] == 6.90 and b31["oas_pb"] == 208.0 and b31["convertible"] is False
    assert b31["plazo_anios"] == pytest.approx(4.72, abs=0.01)
    assert b30["precio_ultimo"] is None and b30["yield_pct"] is None  # 0 = sin dato


def test_leer_prestamos_por_bloques(tmp_path):
    cab = ["Facility Type", "Maturity Date", "Facility Amount", "Country", "Currency", "Issue Date", "RIC", "Base Rate/Spd",
           "Bid Price (%)", "Ask Price (%)", "Mid Price (%)", "Discounted Spread (bps)", "Yield (%)"]
    filas = [["Loans"], ["Issue Date", "Purpose", "Amount Issued", "Facilities"],
             ["28-Oct-2022 Empresa A", "Compra", 7e9, 2], cab,
             ["Revolver/Line >= 1 Yr.", "2027-10-28", 5e8, "United States", "USD", "2022-10-28", "--", "--", 0, 0, 0, 0, 0],
             ["Term Loan B", "2029-10-28", 6.5e9, "United States", "USD", "2022-10-28", "X1", "Term SOFR+725", 0, 0, 0, 0, 0],
             ["02-Mar-2026 Empresa B", "General", 2e10, 1], cab,
             ["Bridge Loan", "2027-03-01", 2e10, "United States", "USD", "2026-03-02", "--", "--", 0, 0, 0, 0, 0],
             ["Total", None, 2.65e10, 3]]
    p = ing.leer_prestamos(crear_xlsx(tmp_path / "l.xlsx", {"Loans": filas}))["facilidades"]
    assert len(p) == 3
    assert p[0]["prestatario"] == "Empresa A" and p[0]["tasa_base_spread"] is None and p[0]["yield_pct"] is None
    assert p[1]["tasa_base_spread"] == "Term SOFR+725"
    assert p[2]["tipo"] == "Bridge Loan" and p[2]["vencimiento"] == "2027-03-01" and p[2]["monto_facilidad_usd"] == 2e10


def test_leer_calendario_deduplica_y_no_suma_calls(tmp_path):
    cab = ["Date", "Event", "Description", "RIC", "ISIN", "Currency", "Native Amount Outstanding", "Amount Outstanding, USD"]
    desc = "SPCX 5.350 07/15/31 '31"
    filas = [cab,
             ["15-Jan-2027", "Coupon", desc, "A=", "US1", "USD", "207,015,278", "207,015,278"],
             ["15-Jan-2027", "Coupon", desc, "B=", "US2", "USD", "207,015,278", "207,015,278"],
             ["2031-06-15", "Call", desc, "A=", "US1", "USD", "7,000,000,000", "7,000,000,000"],
             ["2031-07-15", "Principal", desc, "A=", "US1", "USD", "7,000,000,000", "7,000,000,000"]]
    c = ing.leer_calendario(crear_xlsx(tmp_path / "c.xlsx", {"S": filas}))
    assert len(c["eventos"]) == 3
    assert c["pagos_por_anio_usd"]["2027"]["Coupon"] == 207015278.0
    assert c["pagos_por_anio_usd"]["2031"]["Principal"] == 7e9
    assert "Call" not in c["pagos_por_anio_usd"]["2031"]


# ------------------------------------------------------------------ financieros
def test_leer_estado_secciones_y_valores():
    import pandas as pd
    filas = [["Company Fundamentals - Balance Sheet", None, None], ["Company Name", "X", None], ["Export Date", "2026-10-27 02:29:46", None],
             ["Statement Data", 2026, 2026], ["Period End Date", "2026-06-30", "2026-09-30"], ["Statement Date", "2026-06-29", "2026-09-29"],
             ["Standardized Currency", "USD", "USD"], ["Current Assets", None, None],
             ["Cash & Cash Equivalents", 93522, 51294], ["Debt - Total", "--", 38844], ["Total Assets", None, None], ["Total Assets", 192770, 254045]]
    e = ing.leer_estado(pd.DataFrame(filas))
    assert e["periodos"] == ["2026-06-30", "2026-09-30"] and e["exportado"] == "2026-10-27"
    nombres = [c["concepto"] for c in e["conceptos"]]
    assert nombres == ["Cash & Cash Equivalents", "Debt - Total", "Total Assets"]  # filas de encabezado no son conceptos
    assert e["conceptos"][0]["seccion"] == "Current Assets"
    assert ing.concepto(e, "Debt - Total") == ("2026-09-30", 38844.0)
    assert e["conceptos"][1]["valores"]["2026-06-30"] is None  # '--' = sin dato


def test_leer_estado_con_columna_vacia_al_inicio():
    import pandas as pd
    filas = [[None, "Export Date", "2026-10-27 03:23:18"], [None, "Period End Date", "2026-09-30"], [None, "Revenue", 14575]]
    e = ing.leer_estado(pd.DataFrame(filas))
    assert e["periodos"] == ["2026-09-30"] and e["conceptos"][0]["valores"] == {"2026-09-30": 14575.0}


# ------------------------------------------------------------------ integracion (solo si hay exportes locales)
def test_construir_con_exportes_locales(tmp_path):
    raw = Path(__file__).resolve().parents[1] / "data" / "raw"
    if not any(raw.glob("*.xlsx")):
        pytest.skip("No hay exportes en data/raw (estan fuera del repo por la licencia de LSEG)")
    r = ing.construir(raw, tmp_path)
    assert (tmp_path / "resumen_mercado.json").exists()
    json.loads((tmp_path / "resumen_mercado.json").read_text(encoding="utf-8"))  # JSON valido, sin NaN
    if "ust_6y_pct" in r:
        assert 0 < r["ust_6y_pct"]["valor"] < 20
