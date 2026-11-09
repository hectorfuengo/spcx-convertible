import math

from src import arboles


def test_hull_ejemplo_2_pasos():
    am = arboles.crr(50, 52, 0.05, 0.30, 2, 2, "put", True)[0]
    eu = arboles.crr(50, 52, 0.05, 0.30, 2, 2, "put", False)[0]
    assert math.isclose(am, 7.4284, abs_tol=1e-3)
    assert math.isclose(eu, 6.2457, abs_tol=1e-3)


def test_europea_converge_a_black_scholes():
    eu = arboles.crr(100, 100, 0.04, 0.3, 0.5, 1000, "put", False)[0]
    assert math.isclose(eu, arboles.bs_put(100, 100, 0.04, 0.3, 0.5), abs_tol=0.01)


def test_americana_no_vale_menos_que_europea():
    assert arboles.crr(90, 100, 0.05, 0.4, 1, 200)[0] >= arboles.crr(90, 100, 0.05, 0.4, 1, 200, americana=False)[0]


def test_spcx_replica_reporte_r():
    a = {x["activo"]: x for x in arboles.calcular()["activos"]}["SPCX"]
    assert math.isclose(a["iv_put"], 0.516, abs_tol=0.001)
    assert math.isclose(a["griegas"]["delta"], -0.474, abs_tol=0.002)
    assert a["nodos_ejercicio_4_pasos"] == 3
