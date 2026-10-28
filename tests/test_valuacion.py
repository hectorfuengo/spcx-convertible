"""Pruebas de src/valuacion.py."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import valuacion as val  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def test_valuar_reproduce_molson_coors():
    r = val.valuar(87.61, 0.25, 0.0446, 0.23, 6.0, 0.0575)
    assert r["opcion_por_bono"] == pytest.approx(191.5, abs=0.1)
    assert r["bono_simple_necesario"] == pytest.approx(808.5, abs=0.1)
    assert r["cupon_equilibrio"] == pytest.approx(0.0193, abs=0.00005)


def test_mas_volatilidad_baja_el_cupon_y_mas_prima_lo_sube():
    base = val.valuar(100, 0.25, 0.04, 0.30, 6, 0.07)["cupon_equilibrio"]
    assert val.valuar(100, 0.25, 0.04, 0.50, 6, 0.07)["cupon_equilibrio"] < base
    assert val.valuar(100, 0.40, 0.04, 0.30, 6, 0.07)["cupon_equilibrio"] > base


def test_cupon_de_equilibrio_hace_que_el_convertible_valga_la_par():
    from src.bono import valor_bono_simple
    r = val.valuar(146.9, 0.25, 0.049, 0.45, 6, 0.072)
    bono = valor_bono_simple(r["cupon_equilibrio"], 0.072, 6)["total"]
    assert bono + r["opcion_por_bono"] == pytest.approx(1000.0, abs=1e-6)


def test_prima_para_cupon_cero():
    p = val.prima_para_cupon_cero(146.9, 0.049, 0.5265, 6, 0.072)
    assert p is not None and p > 0.25
    assert val.valuar(146.9, p, 0.049, 0.5265, 6, 0.072)["valor_con_cupon_cero"] == pytest.approx(1000.0, abs=1e-6)
    # con volatilidad bajisima ni con prima 0 se llega a la par
    assert val.prima_para_cupon_cero(146.9, 0.049, 0.01, 6, 0.072) is None


def test_sigma_implicita_base_promedia_call_y_put(tmp_path):
    f = tmp_path / "iv.csv"
    f.write_text("vencimiento,strike,tipo,iv_cierre_pct,interes_abierto,fuente,fecha,estado\n"
                 "2028-12,150,put,50.0,1,x,2026-10-27,dato\n2028-12,150,call,54.0,1,x,2026-10-27,dato\n"
                 "2028-06,150,call,99.0,1,x,2026-10-27,dato\n", encoding="utf-8")
    sigma, _ = val.sigma_implicita_base(f)
    assert sigma == pytest.approx(0.52)
    with pytest.raises(ValueError):
        val.sigma_implicita_base(f, "2030-01")


def test_construir_con_datos_procesados():
    proc = RAIZ / "data" / "processed"
    if not (proc / "resumen_mercado.json").exists():
        pytest.skip("Falta data/processed (corre python -m src.ingesta)")
    out = val.construir(proc, RAIZ / "data" / "opciones_iv.csv")
    json.dumps(out)  # serializable
    assert out["base"]["opcion_por_bono"] + out["base"]["bono_simple_necesario"] == pytest.approx(1000.0)
    assert all(s["estado"] for s in out["supuestos"])
