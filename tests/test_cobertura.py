"""Pruebas de src/cobertura.py y de la IV recalculada de src/valuacion.py."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import cobertura as cob  # noqa: E402
from src import valuacion as val  # noqa: E402
from src.bs import call_price  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def test_note_hedge_cuesta_lo_mismo_que_la_opcion_vendida_en_el_convertible():
    # El note hedge replica la opcion de conversion: su costo = opcion por bono x numero de bonos
    S, prima, r, sig, T = 146.9, 0.25, 0.049, 0.5265, 6.0
    c = cob.cobertura(S, prima, 0.60, r, sig, sig, T, emision_musd=1000.0)
    por_bono = val.valuar(S, prima, r, sig, T, 0.072)["opcion_por_bono"]
    assert c["costo_note_hedge_musd"] == pytest.approx(por_bono * c["bonos_millones"])
    assert c["costo_neto_musd"] == pytest.approx(c["costo_note_hedge_musd"] - c["ingreso_warrants_musd"])
    assert c["costo_neto_musd"] > 0      # los warrants (strike mayor) valen menos que el note hedge


def test_costo_neto_escala_con_la_emision_pero_no_por_bono():
    a = cob.cobertura(146.9, 0.25, 0.6, 0.049, 0.5, 0.5, 6, 500.0)
    b = cob.cobertura(146.9, 0.25, 0.6, 0.049, 0.5, 0.5, 6, 1000.0)
    assert b["costo_neto_musd"] == pytest.approx(2 * a["costo_neto_musd"])
    assert b["costo_neto_por_bono"] == pytest.approx(a["costo_neto_por_bono"])


@pytest.mark.parametrize("ST", [50, 146.9, 183.0])
def test_sin_conversion_no_hay_costo_ni_dilucion(ST):
    e = cob.escenario(ST, 146.9, 183.625, 235.04, 5.4459, 13579.0)
    assert not e["convierte"] and e["valor_por_bono"] == 1000.0
    assert e["costo_sin_cobertura_musd"] == 0 and e["costo_neto_vencimiento_musd"] == 0
    assert e["acciones_nuevas_con_cobertura_millones"] == 0


def test_entre_conversion_y_warrants_la_cobertura_absorbe_todo():
    e = cob.escenario(200.0, 146.9, 183.625, 235.04, 5.4459, 13579.0)
    assert e["convierte"] and e["costo_sin_cobertura_musd"] == pytest.approx((200 - 183.625) * 5.4459)
    assert e["costo_neto_vencimiento_musd"] == pytest.approx(0.0)
    assert e["acciones_nuevas_con_cobertura_millones"] == 0
    assert e["acciones_nuevas_sin_cobertura_millones"] == pytest.approx(5.4459)


def test_por_encima_de_los_warrants_el_emisor_paga_el_exceso():
    X, Kw, acc = 183.625, 235.04, 5.4459
    e = cob.escenario(300.0, 146.9, X, Kw, acc, 13579.0)
    assert e["costo_neto_vencimiento_musd"] == pytest.approx((300 - Kw) * acc)
    assert e["acciones_nuevas_con_cobertura_millones"] == pytest.approx(acc * (1 - Kw / 300))
    assert e["dilucion_con_cobertura_pct"] < e["dilucion_sin_cobertura_pct"]


def test_la_valuacion_a_vencimiento_es_el_maximo_entre_par_y_conversion():
    assert cob.escenario(500, 146.9, 183.625, 235.04, 5.4459, None)["valor_por_bono"] == pytest.approx(500 * 1000 / 183.625)


def test_volatilidad_implicita_recupera_la_sigma_usada():
    S, K, T, r, sig = 141.31, 150.0, 2.2, 0.045, 0.52
    for tipo in ("call", "put"):
        precio = (call_price if tipo == "call" else val.put_price)(S, K, T, r, sig)
        assert val.volatilidad_implicita(precio, S, K, T, r, tipo) == pytest.approx(sig, abs=1e-6)
    assert val.volatilidad_implicita(1000.0, S, K, T, r, "call") is None   # precio imposible


def test_evidencia_tradingview_usa_la_tasa_de_la_curva(tmp_path):
    csv_tv = tmp_path / "tv.csv"
    precio = call_price(141.31, 150.0, 808 / 365, 0.047, 0.52)
    csv_tv.write_text("fecha_consulta,spot,vencimiento,dte,strike,tipo,bid,ask,iv_tradingview_pct,delta,fuente,estado\n"
                      f"2026-11-03,141.31,2029-01-19,808,150,call,{precio - 0.1},{precio + 0.1},58.0,,x,dato\n", encoding="utf-8")
    ust = {"puntos": [{"anios": 1.0, "yield_pct": 4.5}, {"anios": 3.0, "yield_pct": 4.9}]}   # a 2.21 anios: ~4.71%
    f = val.evidencia_tradingview(csv_tv, ust)[0]
    assert f["tasa_usada"] == pytest.approx(0.0471, abs=0.0005)
    assert f["iv_recalculada"] == pytest.approx(0.52, abs=0.005) and f["iv_tradingview"] == pytest.approx(0.58)


def test_construir_cobertura_con_datos_locales():
    proc = RAIZ / "data" / "processed"
    if not (proc / "valuacion.json").exists():
        pytest.skip("Falta data/processed/valuacion.json (corre src.valuacion)")
    out = cob.construir(proc)
    json.dumps(out)
    b = out["base"]
    assert b["costo_note_hedge_musd"] > b["ingreso_warrants_musd"] > 0
    assert len(out["escenarios"]) >= 10 and all(s["estado"] for s in out["supuestos"])
