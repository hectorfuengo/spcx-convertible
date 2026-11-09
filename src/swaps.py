"""Swaps con Boeing (BA), Hull cap. 7: swap de tasas, ventaja comparativa, equity swap sobre BA y cobertura.

Uso:  python -m src.swaps [--processed data/processed] [--docs docs/data]

Replica en Python el cuaderno de Colab de la clase (swaps_hull_cap7_BA.ipynb) con los mismos supuestos y datos:
- Curva SOFR OIS de LSEG (USDSROIS=, 8-nov-2026) y 12 bonos de Boeing (YTW y precio al 6-nov-2026, capturas).
- Los precios de BA salen de Refinitiv (data/processed/precios_ba.json); el cuaderno usa Yahoo Finance.
- Además del cuaderno incluye los datos de apoyo que se usaron para armarlo: curva OIS completa (Curve.xlsx), 42 bonos de
  Boeing (TradingView), estructura de deuda y pares (Refinitiv), resumen de precio y el reporte anual 2025 (10-K).
- No incluye SPY ni ITA ni USD/MXN (no hay datos en el repo): los equity swaps B y C, la cobertura por beta y el swap de
  divisas quedan en el cuaderno y se marcan como pendientes en el JSON.
Escribe swaps.json y lo copia a docs/data/.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np

# ---- Parámetros del cuaderno --------------------------------------------------------------------------------------
OIS = {0.5: 4.1605, 1.0: 4.3215, 1.5: 4.3460, 2.0: 4.3756, 3.0: 4.3702}   # tasas par OIS (%), LSEG, 8-nov-2026
OIS_LARGO = {4.0: 4.3653, 5.0: 4.3637}
R_FREE = 0.040553          # OIS 3M (USDSROIS=, 8-nov-2026)
SOFR_ON = 0.0397           # SOFR overnight, 3-nov-2026
N_TASAS = 100e6            # nocional del swap de tasas (USD)
TASA_FIJA = 0.0430         # HIPOTÉTICA
N_EQ = 10e6                # nocional del equity swap (USD), hipotético
FIN_SPREAD = 0.0050        # HIPOTÉTICO: spread sobre SOFR del equity swap
ACC_BA = 1000              # HIPOTÉTICO: acciones de BA a cubrir
STEP = 63                  # días hábiles por trimestre
LAM = 0.94
HOY = date(2026, 11, 8)
BONOS = [  # vencimiento, cupón %, precio %, YTW %  (capturas del 6-nov-2026)
    ("2027-02-01", 2.700, 99.45, 5.05), ("2027-05-01", 5.040, 99.96, 5.20), ("2027-05-01", 6.259, 100.61, 4.73),
    ("2028-02-01", 3.250, 97.92, 5.00), ("2028-03-01", 3.250, 97.53, 5.21), ("2028-11-01", 3.450, 96.87, 5.13),
    ("2029-03-01", 3.200, 95.74, 5.17), ("2029-05-01", 6.298, 102.37, 5.25),
    ("2030-02-01", 2.950, 92.96, 5.34), ("2030-05-01", 5.150, 99.35, 5.36),
    ("2031-02-01", 3.625, 93.29, 5.42), ("2031-05-01", 6.388, 103.73, 5.41)]
SPREAD_B_VAR = 0.0065      # HIPOTÉTICO: Boeing paga SOFR + 0.65 %
SPREAD_A_VAR = 0.0025      # HIPOTÉTICO: emisor A- paga SOFR + 0.25 %
PRIMA_A_FIJA = 0.0033      # HIPOTÉTICO: emisor A- paga OIS 3A + 33 pb en fija
MARGEN_BANCO = 0.0004      # HIPOTÉTICO: el intermediario cobra 4 pb

# Curva SOFR OIS completa (LSEG USDSROIS=, bid, 8-nov-2026; archivo Curve.xlsx), tasas par en %
OIS_COMPLETA = [("1D", 3.8825), ("7D", 3.8909), ("14D", 3.8874), ("21D", 3.888), ("1M", 3.9052), ("2M", 4.0131), ("3M", 4.0553),
                ("4M", 4.0877), ("5M", 4.1278), ("6M", 4.1605), ("7M", 4.1926), ("8M", 4.2212), ("9M", 4.248), ("10M", 4.274),
                ("11M", 4.3006), ("1Y", 4.3215), ("1Y3M", 4.337), ("1Y6M", 4.346), ("1Y9M", 4.36), ("2Y", 4.3756), ("3Y", 4.3702),
                ("4Y", 4.3653), ("5Y", 4.3637), ("6Y", 4.3731), ("7Y", 4.3842), ("8Y", 4.4098), ("9Y", 4.4295), ("10Y", 4.4587),
                ("11Y", 4.494), ("12Y", 4.5181), ("13Y", 4.549), ("14Y", 4.575), ("15Y", 4.5988), ("20Y", 4.6533), ("25Y", 4.6414),
                ("30Y", 4.6012), ("35Y", 4.541), ("40Y", 4.47), ("45Y", 4.408), ("50Y", 4.334)]

# Bonos listados de Boeing (TradingView, lista de bonos al cierre del 6-nov-2026, 42 filas). Transcritos de captura.
# vencimiento, cupón %, precio %, YTW %, importe pendiente (M USD), emisor
BONOS_TV = [
    ("2043-10-15", 6.875, 102.72, 6.60, 124.99, "BA"), ("2064-05-01", 7.008, 106.10, 6.56, 1500, "BA"), ("2060-05-01", 5.930, 91.91, 6.52, 3500, "BA"),
    ("2047-03-01", 3.650, 68.15, 6.49, 300, "BA"), ("2059-08-01", 3.950, 65.83, 6.47, 1000, "BA"), ("2045-03-01", 3.500, 68.47, 6.46, 250, "BA"),
    ("2059-03-01", 3.825, 64.77, 6.42, 300, "BA"), ("2054-05-01", 6.858, 105.55, 6.42, 2490, "BA"), ("2050-05-01", 5.805, 92.96, 6.39, 5500, "BA"),
    ("2048-11-01", 3.850, 70.31, 6.38, 350, "BA"), ("2048-03-01", 3.625, 68.49, 6.34, 350, "BA"), ("2049-05-01", 3.900, 71.04, 6.33, 800, "BA"),
    ("2050-02-01", 3.750, 68.88, 6.32, 1250, "BA"), ("2043-04-15", 7.875, 115.92, 6.30, 175, "BA"), ("2046-06-15", 3.375, 67.68, 6.25, 400, "BA"),
    ("2040-02-15", 5.875, 98.04, 6.09, 450, "BA"), ("2039-03-15", 6.875, 107.40, 6.01, 500, "BA"), ("2040-05-01", 5.705, 97.27, 6.00, 3000, "BA"),
    ("2038-03-01", 3.550, 80.04, 6.00, 350, "BA"), ("2038-02-15", 6.625, 105.01, 6.00, 300, "BA"), ("2039-03-01", 3.500, 78.64, 5.97, 400, "BA"),
    ("2035-03-01", 3.300, 82.80, 5.95, 250, "BA"), ("2035-02-01", 3.250, 83.86, 5.73, 750, "BA"), ("2033-02-15", 6.125, 102.19, 5.70, 400, "BA"),
    ("2034-05-01", 3.600, 87.41, 5.69, 850, "BA"), ("2034-05-01", 6.528, 105.21, 5.64, 2500, "BA"), ("2027-03-01", 2.800, 99.16, 5.54, 300, "BA"),
    ("2031-09-15", 8.750, 113.57, 5.52, 248, "BA"), ("2031-11-15", 8.625, 113.88, 5.43, 175, "BA"), ("2031-02-01", 3.625, 93.29, 5.42, 1400, "BA"),
    ("2031-05-01", 6.388, 103.73, 5.41, 999.06, "BA"), ("2030-05-01", 5.150, 99.35, 5.36, 4500, "BA"), ("2030-02-01", 2.950, 92.96, 5.34, 750, "BA"),
    ("2028-06-15", 4.600, 98.87, 5.33, 700, "Spirit AeroSystems"), ("2029-05-01", 6.298, 102.37, 5.25, 1500, "BA"), ("2028-03-01", 3.250, 97.53, 5.21, 350, "BA"),
    ("2027-05-01", 5.040, 99.96, 5.20, 2000, "BA"), ("2029-03-01", 3.200, 95.74, 5.17, 1000, "BA"), ("2028-11-01", 3.450, 96.87, 5.13, 350, "BA"),
    ("2027-02-01", 2.700, 99.45, 5.05, 1000, "BA"), ("2028-02-01", 3.250, 97.92, 5.00, 1100, "BA"), ("2027-05-01", 6.259, 100.61, 4.73, 996.9, "BA")]

# Estructura de deuda de Boeing (Refinitiv, Debt & Credit, 8-nov-2026): año, emisiones, vigente (USD), emitido (USD)
DEUDA_RF_VENC = [(2027, 10, 4300000000, 8890899000), (2028, 6, 2730000000, 2730000000), (2029, 5, 2500000000, 6986049000), (2030, 3, 5250000000, 9250000000),
                 (2031, 6, 2824980000, 3824056000), (2033, 1, 400000000, 400000000), (2034, 4, 3350000000, 5841872000), (2035, 2, 1000000000, 1000000000),
                 (2038, 2, 650000000, 650000000), (2039, 2, 900000000, 900000000), (2040, 2, 3450000000, 3450000000), (2042, 1, 100000000, 100000000),
                 (2043, 2, 299990000, 300000000), (2045, 1, 250000000, 250000000), (2046, 1, 400000000, 400000000), (2047, 1, 300000000, 300000000),
                 (2048, 2, 700000000, 700000000), (2049, 1, 800000000, 800000000), (2050, 2, 6750000000, 6750000000), (2054, 3, 2496000000, 4986531000),
                 (2059, 2, 1300000000, 1300000000), (2060, 1, 3500000000, 3500000000), (2064, 3, 1500000000, 2979504000)]
DEUDA_RF = {"bonos_emisiones": 59, "bonos_vigente": 45750970000, "bonos_emitido": 55694911000, "prestamos_emisiones": 4, "prestamos_emitido": 10594000000,
            "total_emisiones": 63, "total_vigente": 45750970000, "total_emitido": 66288911000, "bonos_inactivos": 876, "bonos_inactivos_emitido": 56250429151}
# Panel de deuda de Refinitiv (resumen) y calificaciones
RESUMEN_DEUDA_RF = {"deuda_total_musd": 51500, "caja_musd": 20710, "intereses_pagados_ltm_musd": 2450, "fcf_ltm_musd": 5260, "implicita": "BB- (0.45 %)",
                    "quick_ba": 0.405, "quick_industria": 1.343, "de_industria": 0.42,
                    "calificaciones": [{"agencia": "S&P", "corto": "A-3", "largo": "BBB-", "perspectiva": "Estable"},
                                       {"agencia": "Moody's", "corto": "P-3", "largo": "Baa3 (TradingView)", "perspectiva": "Estable"},
                                       {"agencia": "Fitch", "corto": "F3", "largo": "BBB-", "perspectiva": "Positiva"}]}
# Pares de Boeing (Refinitiv, tabla Peers)
PARES_BA = [("Boeing Co", 0.52, 17.90, -108.92, 290.08, 702.03), ("RTX Corporation", -1.22, 30.79, 19.01, 10.96, 53.98),
            ("Lockheed Martin Corporation", -1.58, 20.14, 12.38, 76.87, 203.70), ("General Dynamics Corp", -0.64, 20.83, 9.90, 17.66, 25.71),
            ("Northrop Grumman Corp", -0.05, 16.57, 10.44, 26.17, 81.34), ("Airbus SE", -1.25, 25.18, -12.44, 21.62, 65.96),
            ("BAE Systems PLC", -1.84, 26.61, None, 18.14, 73.96), ("General Electric Company", 2.70, 36.41, 30.98, 45.37, 110.29)]
# Resumen de precio de BA (captura de cotización; cierre del 6-nov-2026)
PRECIO_BA = {"fecha": "2026-11-06", "cierre": 173.40, "cambio": 0.90, "cambio_pct": 0.52, "cierre_anterior": 172.50, "apertura": 172.00, "bid": "173.35 x 30,000",
             "ask": "173.46 x 20,000", "rango_dia": "169.91 - 174.46", "rango_52s": "165.01 - 254.35", "volumen": 6223766, "volumen_prom": 7849442,
             "cap_mmd": 137.411, "beta_5a": 1.33, "pe_ttm": 17.89, "eps_ttm": 9.69, "dividendo": "0.00 %", "proximos_resultados": "2027-01-26",
             "objetivo_1a": 233.35, "rend_6m_pct": -24.59, "post_mercado": 173.46}
# Del reporte anual 2025 de Boeing (10-K): nota 17 (deuda) y riesgo de mercado
AR2025 = {
    "deuda_total_musd": 54098, "deuda_corto_plazo_musd": 8461, "deuda_total_2024_musd": 53864,
    "tramos": [("2.20 % - 2.50 %, vence hasta 2026", 5899, 6159), ("2.60 % - 3.20 %, hasta 2030", 5088, 5389), ("3.25 % - 3.90 %, hasta 2059", 10136, 9637),
               ("3.95 % - 5.15 %, hasta 2059", 8166, 7462), ("5.71 % - 6.63 %, hasta 2060", 18996, 18987), ("6.86 % - 8.75 %, hasta 2064", 5265, 5577),
               ("Arrendamientos financieros, hasta 2044", 250, 239), ("Otras notas", 298, 414)],
    "amortizaciones": [(2026, 8351), (2027, 4403), (2028, 2739), (2029, 2508), (2030, 5274)],
    "lineas_credito": [("364 días (ago-2026, con opción de extender a ago-2027)", 3000), ("5 años (ago-2028)", 3000), ("5 años (may-2029)", 4000)],
    "disponible_musd": 10000,
    "intereses_incurridos_musd": 2956, "intereses_pagados_musd": 2630,
    "spirit": "En dic-2025 asumió 3,608 M de deuda de Spirit y pagó 2,260 M de inmediato; quedan 300 M de notas al 3.85 % (2026), 700 M al 4.60 % (2028) y 230 M de notas canjeables al 3.25 % (2028, canjeables por acciones de BA).",
    "riesgo_tasa": "Boeing indica que su riesgo de tasa viene principalmente de deuda a tasa fija y que, como los tenedores no pueden exigir el pago anticipado, no lo considera material.",
    "fx": "Cubre pagos y cobros comprometidos y proyectados en moneda extranjera con forwards; un movimiento de 10 % del tipo de cambio cambiaría las ganancias no realizadas en 425 M USD (compensado por la partida cubierta).",
    "materias_primas": "Usa swaps de materias primas; un movimiento de 10 % en el precio cambiaría las ganancias no realizadas en 38 M USD.",
    "riesgos_financiamiento": "Vencimientos de principal por unos 15,500 M USD en los próximos tres años y compromisos de financiamiento de aviones por 15,200 M USD (cifras de los factores de riesgo).",
    "preferentes": "Acciones preferentes convertibles obligatorias Serie A (6.00 %): dividendos de hasta 345 M USD al año hasta la conversión obligatoria del 15-oct-2027; el dividendo común está suspendido desde 2020.",
    "sin_margen": "El reporte no informa el margen (spread) de las líneas de crédito, por eso el margen variable de Boeing en la ventaja comparativa es un supuesto.",
}

# Curva MXN IRS (TIIE) completa (LSEG MXNIRS=, bid; archivo Curve_mxn.xlsx), tasas par en %. Plazo: (etiqueta, años)
MXN_IRS = [("3M", 0.25, 6.545), ("6M", 0.5, 6.425), ("9M", 0.75, 6.625), ("1Y1M", 13 / 12, 6.71), ("2Y2M", 26 / 12, 7.16), ("3Y3M", 39 / 12, 7.46),
           ("4Y4M", 52 / 12, 7.68), ("5Y5M", 65 / 12, 7.83), ("7Y7M", 91 / 12, 8.08), ("10Y10M", 130 / 12, 8.36), ("13Y", 13.0, 8.48),
           ("16Y3M", 195 / 12, 8.645), ("21Y8M", 260 / 12, 8.745), ("32Y6M", 390 / 12, 8.745)]

# Bonos listados de RTX (TradingView, 35 filas, cierre del 6-nov-2026), transcritos de captura.
# vencimiento, cupón %, precio %, YTW % (None = sin dato), vigente (M), moneda, emisor
BONOS_RTX = [
    ("2044-12-15", 4.200, 77.30, 6.32, 262.55, "USD", "RTX"), ("2048-11-16", 4.625, 81.81, 6.14, 1750, "USD", "United Technologies"),
    ("2046-11-01", 3.750, 73.11, 6.09, 1100, "USD", "United Technologies"), ("2054-03-15", 6.400, 103.99, 6.09, 1750, "USD", "RTX"),
    ("2051-09-01", 2.820, 58.37, 6.09, 1000, "USD", "RTX"), ("2047-05-04", 4.050, 76.29, 6.09, 600, "USD", "United Technologies"),
    ("2053-02-27", 5.375, 90.88, 6.07, 1250, "USD", "RTX"), ("2047-04-15", 4.350, 80.14, 6.07, 956.01, "USD", "RTX"),
    ("2050-07-01", 3.125, 63.41, 6.05, 1000, "USD", "RTX"), ("2052-03-15", 3.030, 61.07, 6.05, 1100, "USD", "RTX"),
    ("2045-05-15", 4.150, 79.33, 6.01, 850, "USD", "United Technologies"), ("2042-06-01", 4.500, 85.66, 5.92, 3500, "USD", "United Technologies"),
    ("2041-12-15", 4.700, 89.33, 5.76, 407.2, "USD", "RTX"), ("2040-10-15", 4.875, 91.61, 5.75, 534.04, "USD", "RTX"),
    ("2038-07-15", 6.125, 103.87, 5.66, 575.05, "USD", "United Technologies"), ("2038-11-16", 4.450, 89.56, 5.66, 750, "USD", "United Technologies"),
    ("2040-04-15", 5.700, 101.50, 5.54, 552.92, "USD", "United Technologies"), ("2035-05-01", 5.400, 99.09, 5.53, 446.12, "USD", "United Technologies"),
    ("2036-06-01", 6.050, 104.22, 5.47, 410.38, "USD", "United Technologies"), ("2034-03-15", 6.100, 103.90, 5.43, 1500, "USD", "RTX"),
    ("2033-02-27", 5.150, 99.08, 5.32, 1250, "USD", "RTX"), ("2032-03-15", 2.375, 86.54, 5.29, 1000, "USD", "RTX"),
    ("2031-09-01", 1.900, 85.84, 5.26, 1000, "USD", "RTX"), ("2030-07-01", 2.250, 90.59, 5.11, 1000, "USD", "RTX"),
    ("2031-03-15", 6.000, 103.32, 5.10, 1000, "USD", "RTX"), ("2028-11-16", 4.125, 98.17, 5.08, 3000, "USD", "United Technologies"),
    ("2029-09-15", 7.500, 106.49, 5.02, 414.23, "USD", "United Technologies"), ("2027-05-04", 3.125, 99.14, 4.96, 1100, "USD", "United Technologies"),
    ("2029-01-15", 5.750, 101.55, 4.95, 500, "USD", "RTX"), ("2027-08-15", 7.200, 101.79, 4.85, 318.83, "USD", "RTX"),
    ("2028-08-01", 6.700, 103.07, 4.84, 284.88, "USD", "United Technologies"), ("2027-11-15", 7.100, 102.42, 4.68, 122.75, "USD", "RTX"),
    ("2027-03-15", 3.500, 99.61, 4.64, 1150, "USD", "RTX"), ("2030-05-18", 2.150, 94.59, 3.81, 500, "EUR", "United Technologies"),
    ("2026-11-08", 5.750, 99.94, None, 1250, "USD", "RTX")]
# Estructura de deuda de RTX (Refinitiv, 8-nov-2026): año, emisiones, vigente, emitido (USD)
DEUDA_RTX_VENC = [(2026, 5, 0, 0), (2027, 9, 2916098000, 5798625000), (2028, 5, 3470057000, 8814020000), (2029, 2, 914233000, 1050000000),
                  (2030, 2, 1557150000, 1557150000), (2031, 3, 2000000000, 7000000000), (2032, 1, 1000000000, 1000000000), (2033, 1, 1250000000, 1250000000),
                  (2034, 1, 1500000000, 1500000000), (2035, 1, 446123000, 600000000), (2036, 3, 527942000, 983305000), (2038, 4, 1472698000, 2084016000),
                  (2040, 3, 1152902000, 2134038000), (2041, 2, 424979000, 832199000), (2042, 1, 3500000000, 3500000000), (2043, 2, 399735000, 788192000),
                  (2044, 2, 299839000, 562547000), (2045, 1, 850000000, 850000000), (2046, 3, 1120000000, 1130000000), (2047, 3, 1600000000, 2556014000),
                  (2048, 1, 1750000000, 1750000000), (2050, 1, 1000000000, 1000000000), (2051, 1, 1000000000, 1000000000), (2052, 1, 1100000000, 1100000000),
                  (2053, 1, 1250000000, 1250000000), (2054, 1, 1750000000, 1750000000)]
DEUDA_RTX = {"bonos_emisiones": 58, "bonos_vigente": 34251756000, "bonos_emitido": 41840106000, "prestamos_emisiones": 2, "prestamos_emitido": 10000000000,
             "total_emisiones": 60, "total_vigente": 34251756000, "total_emitido": 51840106000, "bonos_inactivos": 3220, "bonos_inactivos_emitido": 94634587533}
PRECIO_RTX = {"fecha": "2026-11-06", "cierre": 189.53, "cambio": -2.35, "cambio_pct": -1.22, "post_mercado": 190.30, "sp": "BBB+", "moodys": "Baa1", "fitch": "—"}


def curva_cero():
    """Bootstrap de la curva cero continua desde las tasas par OIS, igual que el cuaderno. Devuelve (T, z, factores)."""
    r = {t: v / 100 for t, v in OIS.items()}
    df = {0.5: 1 / (1 + r[0.5] * 0.5), 1.0: 1 / (1 + r[1.0])}
    df[1.5] = (1 - r[1.5] * df[1.0] * 1.0) / (1 + r[1.5] * 0.5)
    df[2.0] = (1 - r[2.0] * df[1.0]) / (1 + r[2.0])
    z2 = -np.log(df[2.0]) / 2.0
    df[3.0] = (1 - r[3.0] * (df[1.0] + df[2.0])) / (1 + r[3.0])
    z3 = -np.log(df[3.0]) / 3.0
    df[2.5] = np.exp(-(z2 + 0.5 * (z3 - z2)) * 2.5)
    T = np.arange(0.5, 3.01, 0.5)
    z = np.array([-np.log(df[t]) / t for t in T])
    return T, z


def swap_tasas():
    T, z = curva_cero()
    dt = 0.5
    Z = np.exp(-z * T)
    Z_ant = np.r_[1.0, Z[:-1]]
    fwd = (Z_ant / Z - 1) / dt
    tasa_par = (1 - Z[-1]) / (dt * Z.sum())

    def valor(shift_pb=0.0, fija=TASA_FIJA):
        """Valor para quien PAGA fija y RECIBE variable (enfoque de bonos)."""
        Zs = np.exp(-(z + shift_pb / 1e4) * T)
        return N_TASAS - ((N_TASAS * fija * dt * Zs).sum() + N_TASAS * Zs[-1])

    v_bonos = valor()
    v_fra = float((N_TASAS * dt * (fwd - TASA_FIJA) * Z).sum())
    dv01 = valor(+0.5) - valor(-0.5)
    flujos = [{"t": float(T[i]), "cero": float(z[i]), "forward": float(fwd[i]), "pago_fijo": N_TASAS * TASA_FIJA * dt,
               "cobro_variable": float(N_TASAS * fwd[i] * dt), "neto": float(N_TASAS * fwd[i] * dt - N_TASAS * TASA_FIJA * dt)}
              for i in range(len(T))]
    sens = [{"pb": int(s), "valor": float(valor(s))} for s in range(-100, 101, 25)]
    return {"nocional": N_TASAS, "tasa_fija": TASA_FIJA, "tasa_par": float(tasa_par), "valor_bonos": float(v_bonos),
            "valor_fra": v_fra, "dv01": float(dv01), "flujos": flujos, "sensibilidad": sens,
            "curva_ois": [{"t": t, "tasa": v} for t, v in {**OIS, **OIS_LARGO}.items()]}


def _anios_tenor(t: str) -> float:
    n, u = int("".join(c for c in t if c.isdigit() or False) or 0), t[-1]
    if "Y" in t and len(t) > 2 and t[-1] != "Y":          # p. ej. 1Y3M
        y, m = t.split("Y")
        return int(y) + int(m.rstrip("M")) / 12
    return {"D": n / 365, "M": n / 12, "Y": float(n)}[u]


def curva_completa():
    return [{"tenor": t, "anios": _anios_tenor(t), "tasa": v} for t, v in OIS_COMPLETA]


def bonos_boeing():
    cur = curva_completa()
    tk = np.array([c["anios"] for c in cur])
    vk = np.array([c["tasa"] for c in cur])
    en_cuaderno = {(v, cup, px, ytw) for v, cup, px, ytw in BONOS}
    filas = []
    for v, cup, px, ytw, imp, emisor in BONOS_TV:
        anios = (date.fromisoformat(v) - HOY).days / 365.25
        ois = float(np.interp(anios, tk, vk))
        filas.append({"vence": v, "cupon": cup, "precio": px, "ytw": ytw, "importe_musd": imp, "emisor": emisor, "boeing": emisor == "BA",
                      "cuaderno": (v, cup, px, ytw) in en_cuaderno, "anios": anios, "ois": ois, "spread_pb": (ytw - ois) * 100})
    base = [f for f in filas if f["cuaderno"]]          # el cuaderno promedia solo estos 12 bonos
    t3 = [f for f in base if 2.0 < f["anios"] < 3.5]
    t5 = [f for f in base if f["anios"] >= 3.5]
    prom = lambda xs, k: float(np.mean([x[k] for x in xs]))
    return filas, {"y3": prom(t3, "ytw") / 100, "sp3": prom(t3, "spread_pb"), "n3": len(t3),
                   "y5": prom(t5, "ytw") / 100, "sp5": prom(t5, "spread_pb"), "n5": len(t5), "n_cuaderno": len(base)}


def bonos_rtx():
    cur = curva_completa()
    tk = np.array([c["anios"] for c in cur]); vk = np.array([c["tasa"] for c in cur])
    filas = []
    for v, cup, px, ytw, imp, mon, emisor in BONOS_RTX:
        anios = (date.fromisoformat(v) - HOY).days / 365.25
        ois = float(np.interp(max(anios, 0), tk, vk))
        filas.append({"vence": v, "cupon": cup, "precio": px, "ytw": ytw, "importe_musd": imp, "moneda": mon, "emisor": emisor, "anios": anios,
                      "ois": ois, "spread_pb": None if ytw is None else (ytw - ois) * 100, "usable": ytw is not None and mon == "USD" and anios > 0})
    # mismo tramo que el cuaderno usa para Boeing: más de 2 y menos de 3.5 años; solo bonos en USD con YTW
    t3 = [f for f in filas if f["usable"] and 2.0 < f["anios"] < 3.5]
    y3 = float(np.mean([f["ytw"] for f in t3])) / 100
    return filas, {"y3": y3, "sp3": float(np.mean([f["spread_pb"] for f in t3])), "n3": len(t3), "bonos_tramo": [f["vence"] + " " + f"{f['cupon']:.3f}" + " %" for f in t3]}


def ventaja_rtx(y3_boeing: float, y3_rtx: float):
    """Misma ventaja comparativa del cuaderno, pero con el rendimiento real de RTX en la parte fija (spreads variables siguen supuestos)."""
    ois3 = OIS[3.0] / 100
    dif_fija = y3_boeing - y3_rtx
    dif_var = SPREAD_B_VAR - SPREAD_A_VAR
    total = dif_fija - dif_var
    g = (total - MARGEN_BANCO) / 2
    return {"fija_a": y3_rtx, "fija_b": y3_boeing, "dif_fija": dif_fija, "dif_var": dif_var, "ganancia_total": total, "margen_banco": MARGEN_BANCO,
            "ganancia_neta": g, "hay_swap": total > MARGEN_BANCO, "dif_var_maxima": dif_fija - MARGEN_BANCO, "spread_a_pb": (y3_rtx - ois3) * 1e4}


def ventaja_comparativa(y3: float):
    ois3 = OIS[3.0] / 100
    fija_b, spread_b = y3, SPREAD_B_VAR
    fija_a, spread_a = ois3 + PRIMA_A_FIJA, SPREAD_A_VAR
    dif_fija, dif_var = fija_b - fija_a, spread_b - spread_a
    total = dif_fija - dif_var
    g_neta = (total - MARGEN_BANCO) / 2
    return {"fija_a": fija_a, "fija_b": fija_b, "spread_a": spread_a, "spread_b": spread_b, "dif_fija": dif_fija, "dif_var": dif_var,
            "ganancia_total": total, "margen_banco": MARGEN_BANCO, "ganancia_neta": g_neta,
            "costo_a": spread_a - g_neta, "costo_b": fija_b - g_neta, "ois3": ois3}


# BA no paga dividendo desde 2020. SPY: Fund Distribution Yield de State Street (1.03 %, al 5-nov-2026; el cuaderno usaba 1.1 %, que es el yield del índice).
# ITA: 12m Trailing Yield de iShares/BlackRock (0.27 %, al 30-sep-2026; el cuaderno usaba 0.8 %). Ambos verificados en las páginas oficiales de los emisores.
DIV_YIELD = {"BA": 0.0, "SPY": 0.0103, "ITA": 0.0027}
DIV_FUENTE = "SPY: Fund Distribution Yield de State Street (5-nov-2026). ITA: 12m Trailing Yield de iShares (30-sep-2026)."
TICKERS = ["BA", "SPY", "ITA"]
# Spot: salida del cuaderno de Colab (Yahoo Finance, 18.6031; 18.60309984 reproduce al peso los flujos que imprime); el FIX de Banxico del 6-nov-2026 (18.6297) coincide a 0.15 %.
# Nocional, cupones del swap y la tasa MXN plana del cuaderno (9 %): HIPOTÉTICOS.
FX = {"spot": 18.60309984, "n_usd": 10e6, "cup_usd": 0.04, "cup_mxn": 0.0875, "r_mxn_plana": 0.09, "spot_fuente": "Cuaderno de Colab (Yahoo Finance); FIX Banxico 6-nov-2026: 18.6297"}


def _precios(processed: Path):
    """Cierres diarios de BA, SPY e ITA (Yahoo, ajustados) del cuaderno; si falta el CSV usa solo BA de Refinitiv."""
    csv = processed.parent / "raw" / "precios_swaps.csv"
    if csv.exists():
        import pandas as pd
        df = pd.read_csv(csv, index_col=0, parse_dates=True)
        out = {t: df[t].dropna().astype(float) for t in TICKERS if t in df}
        return out, "Yahoo Finance (cuaderno, precios ajustados)"
    import pandas as pd
    d = json.loads((processed / "precios_ba.json").read_text(encoding="utf-8"))["datos"]
    return {"BA": pd.Series({x["fecha"]: float(x["cierre"]) for x in d if x.get("cierre")})}, "Refinitiv (solo BA)"


def equity_swaps(processed: Path):
    """Secciones 4 y 5 del cuaderno: equity swaps A (BA contra SOFR+spread), B (BA contra SPY) y C (BA contra ITA),
    valuación a mitad de vida, riesgo (EWMA) y cobertura con swap sobre BA o sobre SPY por beta. Mismo método y mismos
    supuestos que el cuaderno; las posiciones de cada serie se toman desde su propio final, como en el cuaderno."""
    import pandas as pd
    P, fuente = _precios(processed)
    ts = [t for t in TICKERS if t in P]
    S0 = {t: float(P[t].iloc[-1]) for t in ts}
    fechas_ba = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d) for d in P["BA"].index]
    fijo_p = (R_FREE + FIN_SPREAD) * STEP / 252

    def rend_periodos(t, n_per=4):
        v = P[t].values
        pos = [len(v) - 1 - STEP * k for k in range(n_per, -1, -1)]
        obs = v[pos]
        return obs[1:] / obs[:-1] - 1 + DIV_YIELD[t] * STEP / 252, pos

    rBA, pos = rend_periodos("BA")
    out = {"fuente": fuente, "fecha_ultima": fechas_ba[-1], "desde": fechas_ba[0], "n_obs": len(P["BA"]), "s0": S0["BA"],
           "activos": {t: {"ultimo": S0[t], "desde": str(P[t].index[0].date()), "hasta": str(P[t].index[-1].date()), "obs": len(P[t]), "div": DIV_YIELD[t]} for t in ts},
           "tiene_spy_ita": ("SPY" in P and "ITA" in P)}
    rSPY = rend_periodos("SPY")[0] if "SPY" in P else None
    rITA = rend_periodos("ITA")[0] if "ITA" in P else None
    flujos = []
    for i in range(4):
        f = {"periodo": f"{fechas_ba[pos[i]]} → {fechas_ba[pos[i + 1]]}", "rend_ba": float(rBA[i]), "fijo": fijo_p, "neto": float(N_EQ * (rBA[i] - fijo_p))}
        if rSPY is not None:
            f.update({"rend_spy": float(rSPY[i]), "rend_ita": float(rITA[i]), "neto_b": float(N_EQ * (rBA[i] - rSPY[i])), "neto_c": float(N_EQ * (rBA[i] - rITA[i]))})
        flujos.append(f)
    out["flujos"] = flujos
    out["total_neto"] = float(sum(f["neto"] for f in flujos))
    if rSPY is not None:
        out["total_neto_b"] = float(sum(f["neto_b"] for f in flujos))
        out["total_neto_c"] = float(sum(f["neto_c"] for f in flujos))

    # valuación a mitad de vida (pasaron 2 trimestres, quedan 2)
    tt = np.array([1, 2]) * STEP / 252
    cup = N_EQ * fijo_p
    b_fijo = cup * np.exp(-R_FREE * tt[0]) + (cup + N_EQ) * np.exp(-R_FREE * tt[1])

    def ratio(t, k=2):
        v = P[t].values
        s0 = float(v[len(v) - 1 - STEP * k])
        return S0[t] * np.exp(DIV_YIELD[t] * k * STEP / 252) / s0, s0

    rba2, s0ba = ratio("BA")
    mitad = {"s_hace_2_trim": s0ba, "rend_acum": float(rba2 - 1), "valor": float(N_EQ * rba2 - b_fijo), "valor_pct": float((N_EQ * rba2 - b_fijo) / N_EQ), "b_fijo": float(b_fijo)}
    if "SPY" in P and "ITA" in P:
        rs2, rit2 = ratio("SPY")[0], ratio("ITA")[0]
        mitad["tabla"] = [{"swap": "A: BA contra SOFR + spread", "valor": mitad["valor"]},
                          {"swap": "B: BA contra SPY", "valor": float(N_EQ * (rba2 - rs2))}, {"swap": "C: BA contra ITA", "valor": float(N_EQ * (rba2 - rit2))}]
        for r in mitad["tabla"]:
            r["pct"] = r["valor"] / N_EQ
        mitad["rend_acum_spy"], mitad["rend_acum_ita"] = float(rs2 - 1), float(rit2 - 1)
    out["mitad_vida"] = mitad

    # riesgo: covarianza EWMA de los rendimientos log diarios en % (cuaderno: arranca con la covarianza de los primeros 30 días)
    RR = pd.concat({t: 100 * np.log(P[t] / P[t].shift(1)).dropna() for t in ts}, axis=1).dropna()
    X = RR.values
    C = np.cov(X[:30].T)
    for i in range(1, len(X)):
        C = LAM * C + (1 - LAM) * np.outer(X[i - 1], X[i - 1])
    C = np.atleast_2d(C)
    ix = {t: i for i, t in enumerate(ts)}
    vol = {t: float(np.sqrt(252 * C[ix[t], ix[t]]) / 100) for t in ts}
    var10 = lambda sig: float(2.326 * sig * np.sqrt(10 / 252))
    riesgo = {"vol_ewma": vol["BA"], "var99_10d_pct": var10(vol["BA"]), "var99_10d_usd": float(N_EQ * var10(vol["BA"])), "muestra": len(RR), "vol": vol}
    beta = None
    if "SPY" in ts and "ITA" in ts:
        corr = lambda a, b: float(C[ix[a], ix[b]] / np.sqrt(C[ix[a], ix[a]] * C[ix[b], ix[b]]))
        beta = float(C[ix["BA"], ix["SPY"]] / C[ix["SPY"], ix["SPY"]])
        vol_rel = lambda a, b: float(np.sqrt(252 * (C[ix[a], ix[a]] + C[ix[b], ix[b]] - 2 * C[ix[a], ix[b]])) / 100)
        vol_resid = float(np.sqrt(252 * (C[ix["BA"], ix["BA"]] - beta ** 2 * C[ix["SPY"], ix["SPY"]])) / 100)
        filas = [("Swap A: BA contra tasa fija", vol["BA"]), ("Swap B: BA contra SPY", vol_rel("BA", "SPY")), ("Swap C: BA contra ITA", vol_rel("BA", "ITA"))]
        riesgo.update({"tabla": [{"swap": n, "sigma": sg, "var_pct": var10(sg), "var_usd": float(N_EQ * var10(sg))} for n, sg in filas],
                       "corr_ba_spy": corr("BA", "SPY"), "corr_ba_ita": corr("BA", "ITA"), "beta": beta, "vol_resid": vol_resid})
    out["riesgo"] = riesgo

    # cobertura de ACC_BA acciones (3 meses)
    n_cob = ACC_BA * S0["BA"]
    h = 63 / 252
    cob = {"acciones": ACC_BA, "nocional": n_cob, "var99_10d_sin": float(n_cob * var10(vol["BA"])), "carry_3m": float(n_cob * R_FREE * h)}
    if beta is not None:
        cob["var99_10d_spy"] = float(n_cob * var10(riesgo["vol_resid"]))
        cob["vols"] = {"Sin cobertura": vol["BA"], "Swap sobre SPY (β)": riesgo["vol_resid"], "Swap sobre BA": 0.0}
        esc = []
        for m in [-0.10, -0.05, 0.0, 0.05, 0.10]:
            for e in [-0.10, 0.0, 0.10]:
                x = beta * m + e
                sin = n_cob * x
                esc.append({"mercado": m, "propio": e, "sin": float(sin), "con_spy": float(sin + beta * n_cob * (R_FREE * h - m)), "con_ba": float(sin + n_cob * (R_FREE * h - x))})
        cob["matriz"] = esc
    cob["escenarios"] = [{"mov": m, "sin": float(n_cob * m), "con_swap": float(n_cob * R_FREE * h)} for m in [-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20]]
    out["cobertura"] = cob

    # precios base 100 (semanal) para la gráfica
    if len(ts) > 1:
        df = pd.concat({t: P[t] for t in ts}, axis=1).dropna()
        w = df.iloc[::5]
        if w.index[-1] != df.index[-1]:
            w = pd.concat([w, df.iloc[[-1]]])
        out["base100"] = {"fechas": [d.strftime("%Y-%m-%d") for d in w.index], "series": {t: [round(float(x), 2) for x in (100 * w[t] / df[t].iloc[0]).values] for t in ts}}
    return out


def _df_anuales_usd():
    T, z = curva_cero()
    return {int(t): float(np.exp(-zi * t)) for zi, t in zip(z, T) if t in (1.0, 2.0, 3.0)}


def _df_anuales_mxn():
    """Factores de descuento anuales a 1, 2 y 3 años a partir de las tasas par MXN IRS (interpolación lineal y bootstrap anual)."""
    xs = np.array([x[1] for x in MXN_IRS]); ys = np.array([x[2] for x in MXN_IRS]) / 100
    r = {k: float(np.interp(k, xs, ys)) for k in (1, 2, 3)}
    d1 = 1 / (1 + r[1])
    d2 = (1 - r[2] * d1) / (1 + r[2])
    d3 = (1 - r[3] * (d1 + d2)) / (1 + r[3])
    return {1: d1, 2: d2, 3: d3}, r


def swap_divisas():
    """Sección 3 del cuaderno: swap fijo-fijo USD/MXN (recibe USD y paga MXN). Se reproduce la valuación del cuaderno (tasas planas) y se compara
    con una valuación con las curvas reales (SOFR OIS y MXN IRS). El spot es real; nocional y cupones del swap son hipotéticos."""
    from scipy.optimize import brentq
    S0, n_usd, cu, cm = FX["spot"], FX["n_usd"], FX["cup_usd"], FX["cup_mxn"]
    n_mxn = n_usd * S0
    du, (dm, r_mxn_par) = _df_anuales_usd(), _df_anuales_mxn()
    flujos = [{"anio": 0, "usd": -n_usd, "mxn": n_mxn}] + [{"anio": k, "usd": n_usd * cu + (n_usd if k == 3 else 0), "mxn": -(n_mxn * cm + (n_mxn if k == 3 else 0))} for k in (1, 2, 3)]

    def pv(cf, d, desde):
        return sum(c * d[k] / (d[desde] if desde else 1.0) for k, c in cf.items() if k > desde)

    cf_u = {1: n_usd * cu, 2: n_usd * cu, 3: n_usd * cu + n_usd}
    cf_m = {1: n_mxn * cm, 2: n_mxn * cm, 3: n_mxn * cm + n_mxn}

    def valor(S, desde=1):
        return float(pv(cf_u, du, desde) - pv(cf_m, dm, desde) / S)

    try:
        s_eq = float(brentq(valor, 5, 60))
    except Exception:
        s_eq = None
    par = lambda d: float((1 - d[3]) / (d[1] + d[2] + d[3]))
    spots = np.linspace(S0 * 0.8, S0 * 1.3, 40)

    # Valuación del cuaderno: tasas planas continuas (USD = OIS 3M, MXN = 9 % hipotético), un año después (quedan 2 años)
    ru, rm = R_FREE, FX["r_mxn_plana"]

    def valor_plano(S, anios=2):
        ks = np.arange(1, anios + 1)
        b_u = sum(n_usd * cu * np.exp(-ru * k) for k in ks) + n_usd * np.exp(-ru * anios)
        b_m = sum(n_mxn * cm * np.exp(-rm * k) for k in ks) + n_mxn * np.exp(-rm * anios)
        return float(b_u - b_m / S)

    cuaderno = {"r_usd": ru, "r_mxn": rm, "escenarios": [{"spot": float(S0 * k), "valor": valor_plano(S0 * k)} for k in (0.9, 1.0, 1.1, 1.2)],
                "s_equilibrio": float(brentq(valor_plano, 5, 60)), "curva": [{"spot": float(x), "valor": valor_plano(float(x))} for x in spots]}
    return {"spot": S0, "n_usd": n_usd, "n_mxn": n_mxn, "cup_usd": cu, "cup_mxn": cm, "flujos": flujos,
            "valor_inicial": valor(S0, 0), "escenarios": [{"spot": float(S0 * k), "valor": valor(S0 * k)} for k in (0.9, 1.0, 1.1, 1.2)], "s_equilibrio": s_eq,
            "curva": [{"spot": float(x), "valor": valor(x)} for x in spots],
            "cuaderno": cuaderno, "par_usd_3a": par(du), "par_mxn_3a": par(dm),
            "df_usd": {str(k): v for k, v in du.items()}, "df_mxn": {str(k): v for k, v in dm.items()}, "par_mxn_interp": {str(k): v for k, v in r_mxn_par.items()},
            "curva_mxn": [{"tenor": t, "anios": a_, "tasa": v} for t, a_, v in MXN_IRS],
            "estado": "dato (curvas y spot) / supuesto (cupones y nocional del swap)"}


def construir(processed: Path) -> dict:
    bonos, tramos = bonos_boeing()
    return {
        "fecha_curva": "2026-11-08", "fecha_bonos": "2026-11-06",
        "supuestos": {"nocional_tasas": N_TASAS, "tasa_fija": TASA_FIJA, "nocional_equity": N_EQ, "fin_spread": FIN_SPREAD, "r_free": R_FREE, "sofr_on": SOFR_ON,
                      "acciones_ba": ACC_BA, "spread_var_boeing": SPREAD_B_VAR, "spread_var_a": SPREAD_A_VAR, "prima_a_fija": PRIMA_A_FIJA, "margen_banco": MARGEN_BANCO},
        "tasas": swap_tasas(),
        "bonos": bonos, "tramos": tramos, "curva_ois": curva_completa(),
        "deuda_refinitiv": {**DEUDA_RF, "vencimientos": [{"anio": a, "emisiones": n, "vigente": v, "emitido": e} for a, n, v, e in DEUDA_RF_VENC], "resumen": RESUMEN_DEUDA_RF},
        "pares": [{"nombre": n, "cambio_pct": c, "pe": pe, "crec_eps_pct": g, "roe_pct": r, "de_pct": d} for n, c, pe, g, r, d in PARES_BA],
        "precio_ba": PRECIO_BA,
        "ar2025": {**AR2025, "tramos": [{"tramo": t, "a2025": a, "a2024": b} for t, a, b in AR2025["tramos"]],
                   "amortizaciones": [{"anio": a, "musd": m} for a, m in AR2025["amortizaciones"]],
                   "lineas_credito": [{"linea": l, "musd": m} for l, m in AR2025["lineas_credito"]]},
        "ventaja": ventaja_comparativa(tramos["y3"]),
        "rtx": {"bonos": bonos_rtx()[0], "tramo": bonos_rtx()[1], "ventaja": ventaja_rtx(tramos["y3"], bonos_rtx()[1]["y3"]),
                "deuda": {**DEUDA_RTX, "vencimientos": [{"anio": a, "emisiones": n, "vigente": v, "emitido": e} for a, n, v, e in DEUDA_RTX_VENC]}, "precio": PRECIO_RTX},
        "equity": equity_swaps(processed), "divisas": swap_divisas(),
        "pendiente": [
            "Cupones del swap de divisas (4.00 % en USD y 8.75 % en MXN) y nocional de 10 M USD: son los términos del contrato de ejemplo, no un dato de mercado. Para que el swap valga cero hoy, los cupones serían los de la tasa par de cada curva (ver sección 3).",
            "Margen variable de Boeing y de RTX (SOFR + 0.65 % y + 0.25 %): el reporte 2025 de Boeing no informa el margen de sus líneas de crédito y no hay dato público comparable. De la diferencia entre ambos depende si el swap conviene (ver la ventaja comparativa con RTX, donde el umbral es de 22 pb).",
            "Spread del equity swap (SOFR + 0.50 %) y costo de préstamo de BA: son cotizaciones de mesa o de prime broker y no se publican.",
        ],
        "fuente": "Cuaderno swaps_hull_cap7_BA.ipynb (Hull cap. 7); curva SOFR OIS de LSEG (Curve.xlsx, 8-nov-2026); bonos de Boeing de TradingView (6-nov-2026); estructura de deuda, pares y resumen de deuda de Refinitiv (8-nov-2026); reporte anual 2025 de Boeing (10-K); precios diarios de BA de Refinitiv.",
        "estado": "dato (curva, bonos, precios) / hipotético (spreads, nocionales, tasa fija, posición)",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--docs", default="docs/data")
    a = ap.parse_args(argv)
    processed = Path(a.processed)
    d = construir(processed)
    ruta = processed / "swaps.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(ruta, docs / "swaps.json")
    print("Escrito", ruta)


if __name__ == "__main__":
    main()
