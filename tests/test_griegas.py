"""Pruebas de src/griegas.py."""
import json
import sys
from math import exp
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import griegas as gr  # noqa: E402
from src.bs import call_price, put_price  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
S, K, T, R, SIG = 141.31, 150.0, 808 / 365, 0.047, 0.53


def test_unidades_coinciden_con_diferencias_finitas():
    g = gr.griegas_unidades(S, K, T, R, SIG, "call")
    assert g["delta"] == pytest.approx((call_price(S + 0.01, K, T, R, SIG) - call_price(S - 0.01, K, T, R, SIG)) / 0.02, rel=1e-4)
    assert g["vega"] == pytest.approx(call_price(S, K, T, R, SIG + 0.005) - call_price(S, K, T, R, SIG - 0.005), rel=1e-3)   # por 1 punto
    assert g["rho"] == pytest.approx(call_price(S, K, T, R + 0.005, SIG) - call_price(S, K, T, R - 0.005, SIG), rel=1e-3)  # por 1 punto
    un_dia = 1 / 365
    assert g["theta"] == pytest.approx(call_price(S, K, T - un_dia, R, SIG) - call_price(S, K, T, R, SIG), rel=2e-2)           # por día


def test_paridad_delta_y_gamma_vega_iguales_en_call_y_put():
    c, p = gr.griegas_unidades(S, K, T, R, SIG, "call"), gr.griegas_unidades(S, K, T, R, SIG, "put")
    assert c["delta"] - p["delta"] == pytest.approx(1.0)
    assert c["gamma"] == pytest.approx(p["gamma"]) and c["vega"] == pytest.approx(p["vega"])
    assert put_price(S, K, T, R, SIG) == pytest.approx(call_price(S, K, T, R, SIG) - S + K * exp(-R * T), rel=1e-6)


def test_posicion_larga_y_corta_son_opuestas():
    a, b = gr.posicion(S, K, T, R, SIG, 5.0, +1), gr.posicion(S, K, T, R, SIG, 5.0, -1)
    assert all(a[k] == pytest.approx(-b[k]) for k in a)


def _csv(tmp_path, filas):
    cab = "fecha_captura,hora_captura_mty,spot,vencimiento,dte,tipo,strike,bid,ask,last,volumen,interes_abierto,iv_bid_pct,iv_mid_pct,iv_ask_pct,delta,gamma,vega,theta,fuente,estado\n"
    ruta = tmp_path / "g.csv"
    ruta.write_text(cab + "\n".join(filas) + "\n", encoding="utf-8")
    return ruta


UST = {"puntos": [{"anios": 1.0, "yield_pct": 4.5}, {"anios": 3.0, "yield_pct": 4.9}]}


def test_fila_sin_griegas_se_calcula_con_la_iv_del_punto_medio(tmp_path):
    mid = put_price(S, 140.0, 808 / 365, 0.0471, 0.55)
    ruta = _csv(tmp_path, [f"2026-11-03,20:02,{S},2029-01-19,808,put,140,{mid - 0.5},{mid + 0.5},{mid},1,1,,,,,,,,x,dato"])
    o = gr.opciones_listadas(ruta, UST)[0]
    assert o["lseg"] is None and o["iv_lseg"] is None
    assert o["iv_punto_medio"] == pytest.approx(0.55, abs=0.005) and o["propias"]["delta"] < 0


def test_fila_con_griegas_compara_contra_lseg(tmp_path):
    g = gr.griegas_unidades(S, K, 808 / 365, 0.0471, 0.53, "call")
    ruta = _csv(tmp_path, [f"2026-11-03,19:57,{S},2029-01-19,808,call,150,44,46,45,1,1,52,53,54,{g['delta']},{g['gamma']},{g['vega']},{g['theta']},x,dato"])
    o = gr.opciones_listadas(ruta, UST)[0]
    assert abs(o["dif"]["delta"]) < 1e-3 and abs(o["dif"]["vega"]) < 1e-3
    assert gr.resumen_diferencias([o])["call 2029-01-19"]["delta"]["n"] == 1


def test_datos_locales():
    proc = RAIZ / "data" / "processed"
    csv_ = RAIZ / "data" / "opciones_refinitiv_griegas.csv"
    if not (proc / "cobertura.json").exists() or not csv_.exists():
        pytest.skip("Faltan datos procesados")
    out = gr.construir(proc, csv_)
    json.dumps(out)
    pos = out["convertible"]["posiciones"]
    # el note hedge cancela la opción de conversión; el neto es solo los warrants vendidos
    for k in pos["emisor_con_cobertura"]:
        assert pos["emisor_con_cobertura"][k] == pytest.approx(pos["warrants_vendidos"][k])
        assert pos["opcion_conversion_vendida"][k] == pytest.approx(-pos["note_hedge_comprado"][k])
    # diferencia media entre el cálculo propio y LSEG: pequeña
    for d in out["diferencias"].values():
        assert abs(d["delta"]["media"]) < 0.02
