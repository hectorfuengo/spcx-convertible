"""Conciliación de la deuda de Refinitiv contra la nota 9 del 10-Q (30-sep-2026)."""
import json
from pathlib import Path

A = json.loads(Path("data/processed/analisis.json").read_text())["deuda"]


def test_refinitiv_cuadra_con_10q():
    c = A["nota9_10q"]["conciliacion"]
    assert c["deuda_total_refinitiv"] == c["deuda_total_10q"] == 38844
    assert c["cp_refinitiv"] == c["cp_10q"] and c["lp_refinitiv"] == c["lp_10q"]
    assert c["spacex_notes_refinitiv"] == c["spacex_notes_10q"] == 25000
    assert abs(c["cupon_ponderado_refinitiv"] - c["cupon_ponderado_10q"]) < 0.001


def test_vencimientos_suman_el_principal_total():
    n9 = A["nota9_10q"]
    assert sum(v for _, v in n9["vencimientos"]) == n9["total_deuda"][0] == 38006
    assert sum(r[1] for r in n9["deuda"]) == 38006


def test_el_muro_no_cuenta_facilidades_pagadas():
    vig = {f["monto_musd"] for f in A["facilidades"] if f["estado_10q"] == "vigente"}
    assert 20000 not in vig and 5000 in vig
    assert sum(m["facilidades_musd"] for m in A["muro_vencimientos"]) == 5000


def test_segmentos_3t_cuadran_con_refinitiv():
    e = json.loads(Path("data/empresa.json").read_text())["q3_2026_musd"]["ingresos"]
    assert e["Space"] + e["Connectivity"] + e["SI"] == e["total"] == 14575
