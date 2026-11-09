from pathlib import Path
import math

from src import swaps


def test_swap_tasas_bonos_igual_a_fras():
    t = swaps.swap_tasas()
    assert math.isclose(t["valor_bonos"], t["valor_fra"], rel_tol=1e-9)


def test_tasa_par_hace_cero_el_swap():
    t = swaps.swap_tasas()
    T, z = swaps.curva_cero()
    Z = [math.exp(-zi * ti) for zi, ti in zip(z, T)]
    valor = swaps.N_TASAS * (1 - Z[-1]) - swaps.N_TASAS * t["tasa_par"] * 0.5 * sum(Z) * 1 + 0
    assert abs(valor) < 1e-3 * swaps.N_TASAS


def test_pagador_de_fija_gana_si_suben_las_tasas():
    t = swaps.swap_tasas()
    assert t["dv01"] > 0
    assert t["tasa_fija"] < t["tasa_par"] and t["valor_bonos"] > 0


def test_ventaja_comparativa_reparte_ganancia():
    v = swaps.ventaja_comparativa(0.0528)
    assert math.isclose(v["ganancia_total"], v["dif_fija"] - v["dif_var"])
    assert math.isclose(v["costo_b"], v["fija_b"] - v["ganancia_neta"])


def test_datos_de_apoyo_cuadran_con_las_capturas():
    d = swaps.construir(__import__("pathlib").Path("data/processed"))
    assert len(d["bonos"]) == 42 and sum(b["cuaderno"] for b in d["bonos"]) == 12
    assert sum(1 for b in d["bonos"] if not b["boeing"]) == 1                      # la fila de Spirit
    dr = d["deuda_refinitiv"]
    assert sum(v["vigente"] for v in dr["vencimientos"]) == dr["total_vigente"]
    assert sum(v["emisiones"] for v in dr["vencimientos"]) == dr["total_emisiones"]
    assert sum(t["a2025"] for t in d["ar2025"]["tramos"]) == d["ar2025"]["deuda_total_musd"]
    assert len(d["curva_ois"]) == 40 or len(d["curva_ois"]) == 41


def test_promedios_de_tramos_son_los_del_cuaderno():
    t = swaps.bonos_boeing()[1]
    assert t["n3"] == 4 and t["n5"] == 2
    assert abs(t["y3"] - 0.0528) < 1e-9 and abs(t["y5"] - 0.05415) < 1e-9


def test_equity_swaps_b_y_c_con_precios_de_yahoo():
    from pathlib import Path
    e = swaps.equity_swaps(Path("data/processed"))
    assert e["tiene_spy_ita"] and len(e["flujos"]) == 4 and e["n_obs"] == 499
    for f in e["flujos"]:
        assert math.isclose(f["neto_b"], swaps.N_EQ * (f["rend_ba"] - f["rend_spy"]), rel_tol=1e-9)
        assert math.isclose(f["neto_c"], swaps.N_EQ * (f["rend_ba"] - f["rend_ita"]), rel_tol=1e-9)
    assert abs(e["s0"] - 173.40) < 0.01                                    # coincide con el cierre de TradingView/Refinitiv del 6-nov


def test_cobertura_con_swap_sobre_ba_deja_pnl_constante():
    from pathlib import Path
    c = swaps.equity_swaps(Path("data/processed"))["cobertura"]
    assert len({round(r["con_ba"], 6) for r in c["matriz"]}) == 1
    assert c["var99_10d_spy"] < c["var99_10d_sin"]


def test_swap_divisas_vale_cero_en_el_tipo_de_cambio_de_equilibrio():
    d = swaps.swap_divisas()
    assert d["s_equilibrio"] is not None
    cerca = min(d["curva"], key=lambda x: abs(x["spot"] - d["s_equilibrio"]))
    assert abs(cerca["valor"]) < 0.1 * d["n_usd"]


def test_rtx_bonos_y_deuda_cuadran():
    d = swaps.construir(Path("data/processed"))["rtx"]
    assert len(d["bonos"]) == 35 and d["tramo"]["n3"] == 3
    assert abs(d["tramo"]["y3"] - 0.050167) < 1e-5
    assert sum(v["vigente"] for v in d["deuda"]["vencimientos"]) == d["deuda"]["total_vigente"] == 34251756000
    assert sum(v["emisiones"] for v in d["deuda"]["vencimientos"]) == d["deuda"]["total_emisiones"]


def test_ventaja_con_rtx_desaparece_con_los_spreads_del_cuaderno():
    v = swaps.ventaja_rtx(0.0528, 0.0502)
    assert not v["hay_swap"] and v["ganancia_total"] < 0
    assert swaps.ventaja_rtx(0.0528, 0.0450)["hay_swap"]


def test_swap_divisas_con_curva_mxn():
    d = swaps.swap_divisas()
    assert 0.07 < d["par_mxn_3a"] < 0.08 and 0.04 < d["par_usd_3a"] < 0.045
    assert d["df_mxn"]["1"] > d["df_mxn"]["2"] > d["df_mxn"]["3"]


def test_swap_divisas_reproduce_la_salida_del_cuaderno():
    d = swaps.swap_divisas()
    assert round(d["spot"], 4) == 18.6031
    v = [round(e["valor"]) for e in d["cuaderno"]["escenarios"]]
    assert v == [-1007491, 90648, 989125, 1737857]
    assert abs(d["cuaderno"]["s_equilibrio"] - 18.434) < 0.001
    # flujos del cuaderno (el spot del cuaderno solo se conoce a 4 decimales: tolerancia de 2 MXN sobre cientos de millones)
    mxn = [f["mxn"] for f in d["flujos"]]
    assert abs(mxn[0] - 186030998) < 2 and abs(mxn[1] + 16277712) < 2 and abs(mxn[3] + 202308711) < 2
