"""Pruebas de src/analisis.py."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import analisis as an  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _fin(**vals):
    conceptos = [{"concepto": an.CONCEPTOS[k], "seccion": "x", "valores": {"2026-09-30": v}} for k, v in vals.items()]
    return {"hojas": {"h": {"conceptos": conceptos}}}


def test_razones_basicas():
    fin = _fin(deuda_total=100.0, activos=400.0, capital=200.0, ebit=30.0, intereses=10.0, ebitda=50.0, ingresos=100.0,
               deuda_neta=-20.0, activo_circulante=90.0, pasivo_circulante=30.0, utilidad_neta=10.0, pasivos=200.0)
    r = an.razones_periodo(fin, "2026-09-30", factor_anual=4)["razones"]
    assert r["deuda_sobre_activos"] == pytest.approx(0.25) and r["deuda_sobre_capital"] == pytest.approx(0.5)
    assert r["cobertura_intereses"] == pytest.approx(3.0) and r["razon_circulante"] == pytest.approx(3.0)
    assert r["deuda_neta_sobre_ebitda"] == pytest.approx(-20 / 200) and r["margen_ebitda"] == pytest.approx(0.5)


def test_dato_faltante_da_none_y_no_falla():
    r = an.razones_periodo(_fin(activos=400.0), "2026-09-30")["razones"]
    assert r["deuda_sobre_activos"] is None and r["margen_neto"] is None


def test_deuda_total_se_arma_de_corto_y_largo_plazo():
    r = an.razones_periodo(_fin(deuda_cp=10.0, deuda_lp=90.0, activos=200.0), "2026-09-30")
    assert r["cifras"]["deuda_total"] == 100.0 and r["razones"]["deuda_sobre_activos"] == pytest.approx(0.5)


def test_analisis_con_datos_locales():
    proc = RAIZ / "data" / "processed"
    if not (proc / "financieros_trimestral.json").exists():
        pytest.skip("Faltan datos procesados (corre src.ingesta)")
    out = an.construir(proc)
    json.dumps(out)
    b = out["deuda"]["balance"]
    assert b["cuadra"] and b["deuda_corto_plazo"] + b["deuda_largo_plazo"] == b["deuda_total"]
    assert sum(m["principal_bonos_musd"] for m in out["deuda"]["muro_vencimientos"]) == pytest.approx(25000.0)
    assert any(f["es_spcx"] for f in out["comparables"]["filas"])
