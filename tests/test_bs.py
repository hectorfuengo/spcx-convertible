"""Pruebas de Black-Scholes con valores de referencia generales (sin datos del caso).

Valor de libro de texto (Hull): S=42, K=40, r=10%, sigma=20%, T=0.5
    call = 4.76, put = 0.81
Las pruebas del caso Molson Coors se agregan en test_molson_coors.py
cuando se tengan los parametros verificados del PDF.
"""
import sys
from math import exp
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bs import call_price, greeks, put_price  # noqa: E402

S, K, T, R, SIGMA = 42.0, 40.0, 0.5, 0.10, 0.20


def test_call_libro_de_texto():
    assert call_price(S, K, T, R, SIGMA) == pytest.approx(4.76, abs=0.01)


def test_put_libro_de_texto():
    assert put_price(S, K, T, R, SIGMA) == pytest.approx(0.81, abs=0.01)


@pytest.mark.parametrize("spot,strike,plazo,tasa,vol", [
    (100, 100, 1.0, 0.05, 0.25),
    (50, 60, 2.0, 0.03, 0.40),
    (120, 90, 0.25, 0.08, 0.15),
])
def test_paridad_put_call(spot, strike, plazo, tasa, vol):
    c = call_price(spot, strike, plazo, tasa, vol)
    p = put_price(spot, strike, plazo, tasa, vol)
    assert c - p == pytest.approx(spot - strike * exp(-tasa * plazo), abs=1e-9)


def test_delta_call_menos_put_es_uno():
    dc = greeks(S, K, T, R, SIGMA, "call")["delta"]
    dp = greeks(S, K, T, R, SIGMA, "put")["delta"]
    assert dc - dp == pytest.approx(1.0, abs=1e-12)


def test_delta_coincide_con_derivada_numerica():
    h = 1e-4
    num = (call_price(S + h, K, T, R, SIGMA) - call_price(S - h, K, T, R, SIGMA)) / (2 * h)
    assert greeks(S, K, T, R, SIGMA, "call")["delta"] == pytest.approx(num, abs=1e-6)


def test_vega_y_gamma_coinciden_con_derivada_numerica():
    h = 1e-4
    vega_num = (call_price(S, K, T, R, SIGMA + h) - call_price(S, K, T, R, SIGMA - h)) / (2 * h)
    gamma_num = (call_price(S + h, K, T, R, SIGMA) - 2 * call_price(S, K, T, R, SIGMA)
                 + call_price(S - h, K, T, R, SIGMA)) / h**2
    g = greeks(S, K, T, R, SIGMA, "call")
    assert g["vega"] == pytest.approx(vega_num, rel=1e-5)
    assert g["gamma"] == pytest.approx(gamma_num, rel=1e-4)


def test_entradas_invalidas():
    with pytest.raises(ValueError):
        call_price(-1, K, T, R, SIGMA)
    with pytest.raises(ValueError):
        greeks(S, K, T, R, SIGMA, "otra")
