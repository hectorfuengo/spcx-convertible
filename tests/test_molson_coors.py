"""Validacion contra el caso Molson Coors (Teaching Notes NE90-06-107, Tec de Monterrey).

Los valores esperados vienen del PDF y se comparan con la precision con que aparecen
impresos (por eso las tolerancias). Pagina de cada dato entre parentesis.

Notas sobre inconsistencias del propio PDF, que NO se usan como prueba:
  - Delta del call: 0.64 (Exhibit 2, p. 8) vs 0.63 (Exhibit 4, p. 9). El calculo da 0.6408.
  - Warrants (p. 10): el call de 11.4 corresponde a sigma = 21%, pero el put (32.8) y el
    delta (0.47) corresponden a sigma = 23%. Al 21% salen put 31.09 y delta 0.446.
  - Costo del note hedge: 106.7 (Exhibit 1, p. 5-7) vs 110 (Exhibit 4, p. 9); ingreso por
    warrants: 57.0 (p. 5-7) vs 59 (p. 10). Dependen de redondeos y de las acciones usadas.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bono import cupon_de_equilibrio, valor_bono_simple  # noqa: E402
from src.bs import call_price, greeks, put_price  # noqa: E402

# Supuestos del caso (Teaching Notes p. 2; Exhibit 2, p. 8)
S = 87.61          # precio de la accion al cierre del 11-jun-2007
PRIMA = 0.25       # prima de conversion
X = 109.51         # precio de conversion
R = 0.0446         # tasa libre de riesgo (Treasury a 5 anios)
SIGMA = 0.23       # volatilidad anualizada
T = 6.0            # anios al vencimiento
YTM = 0.0575       # tasa de descuento del bono simple
NOMINAL = 1000.0


def test_precio_de_conversion():
    assert S * (1 + PRIMA) == pytest.approx(X, abs=0.01)


def test_call_por_accion():
    # p. 8: Call Value $21.0 (la hoja usa 20.97, ver Teaching Notes)
    assert call_price(S, X, T, R, SIGMA) == pytest.approx(21.0, abs=0.05)


def test_put_por_accion():
    # p. 8: Put Value $17.2 (por paridad put-call)
    assert put_price(S, X, T, R, SIGMA) == pytest.approx(17.2, abs=0.05)


def test_delta_del_call():
    # p. 8: 0.64
    assert greeks(S, X, T, R, SIGMA)["delta"] == pytest.approx(0.64, abs=0.005)


def test_acciones_por_bono():
    # p. 8: 9.13 acciones
    assert NOMINAL / X == pytest.approx(9.13, abs=0.005)


def test_valor_de_la_opcion_de_conversion_por_bono():
    # p. 8: 191.5 = call por accion x acciones por bono
    valor = call_price(S, X, T, R, SIGMA) * NOMINAL / X
    assert valor == pytest.approx(191.5, abs=0.1)


def test_opcion_por_bono_con_subyacente_800():
    # p. 8, segunda tabla: S = 800 (= 87.61 x 9.13), X = 1000
    assert call_price(800, 1000, T, R, SIGMA) == pytest.approx(191.5, abs=0.1)
    assert put_price(800, 1000, T, R, SIGMA) == pytest.approx(156.7, abs=0.1)


def test_bono_simple_con_cupon_1_93():
    # p. 9, Exhibit 3: cupones 96.8, principal 711.7, total 808.5
    v = valor_bono_simple(0.0193, YTM, 6, NOMINAL)
    assert v["cupones"] == pytest.approx(96.8, abs=0.05)
    assert v["principal"] == pytest.approx(711.7, abs=0.05)
    assert v["total"] == pytest.approx(808.5, abs=0.05)


def test_convertible_vale_mil():
    # p. 9: bono simple (808.5) + opcion (191.5) = 1,000
    opcion = call_price(S, X, T, R, SIGMA) * NOMINAL / X
    bono = valor_bono_simple(0.0193, YTM, 6, NOMINAL)["total"]
    assert bono + opcion == pytest.approx(1000.0, abs=0.1)


def test_cupon_de_equilibrio_es_1_93():
    # p. 3 y p. 9: el cupon que hace que el convertible valga exactamente 1,000
    opcion = call_price(S, X, T, R, SIGMA) * NOMINAL / X
    cupon = cupon_de_equilibrio(NOMINAL - opcion, YTM, 6, NOMINAL)
    assert cupon == pytest.approx(0.0193, abs=0.00005)


def test_call_del_warrant_al_60_por_ciento():
    # p. 10: strike 140.2, sigma 21% -> call 11.4
    assert call_price(S, 140.2, T, R, 0.21) == pytest.approx(11.4, abs=0.05)
