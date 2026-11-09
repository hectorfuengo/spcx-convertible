"""Árbol binomial CRR para puts americanas (tarea de clase del 21-oct-2026): SPCX, TSLA, MU, SPY y NQ.

Uso:  python -m src.arboles [--out data/processed] [--docs docs/data]

Replica en Python el R Markdown de la clase (CLASE_21_Oct_26 - Árboles). Datos de entrada: capturas de la cadena
del 21-oct-2026, vencimiento 20-nov-2026 (30 días). Escribe arboles.json, que lee la pestaña "Árboles" del sitio.

Unidades de las griegas (igual que el Rmd): theta por día, vega y rho por 1 punto.
"""
from __future__ import annotations

import argparse
import json
import shutil
from math import erf, exp, log, sqrt
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

R = 0.0509      # rendimiento del Tesoro a 10 años usado en la tarea (CNBC)
T = 30 / 365    # 21-oct a 20-nov-2026

# activo, S0, K, call_bid, call_ask, put_bid, put_ask, IV de la plataforma (%), es_futuro
MERCADO = [
    ("SPCX", 159.31, 160, 9.15, 9.45, 9.30, 9.60, 59.91, False),
    ("TSLA", 386.47, 385, 20.10, 20.70, 17.30, 17.85, 59.08, False),
    ("MU", 913.67, 915, 53.40, 55.10, 50.70, 53.30, 59.85, False),
    ("SPY", 773.09, 773, 13.39, 13.49, 10.58, 10.60, 16.88, False),
    ("NQ", 29773, 29750, 738, 752, 719, 728, 21.64, True),
]


def _ncdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def crr(S0, K, r, sigma, T, N, tipo="put", americana=True, q=0.0, fut=False):
    """Árbol CRR. Devuelve (precio, niveles 0-2, u, d, p, dt). fut=True: opción sobre futuro (q = r)."""
    if fut:
        q = r
    dt = T / N
    u = exp(sigma * sqrt(dt))
    d = 1 / u
    p = (exp((r - q) * dt) - d) / (u - d)
    disc = exp(-r * dt)
    sg = 1 if tipo == "call" else -1
    j = np.arange(N + 1)
    V = np.maximum(sg * (S0 * u ** (N - j) * d**j - K), 0.0)
    niveles = {}
    if N <= 2:
        niveles[N] = V.copy()
    for i in range(N - 1, -1, -1):
        k = np.arange(i + 1)
        cont = disc * (p * V[: i + 1] + (1 - p) * V[1 : i + 2])
        if americana:
            Si = S0 * u ** (i - k) * d**k
            V = np.maximum(cont, np.maximum(sg * (Si - K), 0.0))
        else:
            V = cont
        if i <= 2:
            niveles[i] = V.copy()
    return float(V[0]), niveles, u, d, p, dt


def bs_put(S0, K, r, sigma, T, q=0.0):
    d1 = (log(S0 / K) + (r - q + sigma**2 / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * _ncdf(-d2) - S0 * exp(-q * T) * _ncdf(-d1)


def iv_arbol(precio, S0, K, r, T, tipo, fut=False, N=500):
    return brentq(lambda s: crr(S0, K, r, s, T, N, tipo, True, 0.0, fut)[0] - precio, 0.01, 3.0, xtol=1e-10)


def griegas(S0, K, r, sigma, T, N=500, tipo="put", americana=True, q=0.0, fut=False):
    f0, niv, u, d, _, dt = crr(S0, K, r, sigma, T, N, tipo, americana, q, fut)
    f1, f2 = niv[1], niv[2]
    S11, S10 = S0 * u, S0 * d
    S22, S21, S20 = S0 * u**2, S0, S0 * d**2
    delta = (f1[0] - f1[1]) / (S11 - S10)
    gamma = ((f2[0] - f2[1]) / (S22 - S21) - (f2[1] - f2[2]) / (S21 - S20)) / (0.5 * (S22 - S20))
    theta = (f2[1] - f0) / (2 * dt) / 365
    vega = crr(S0, K, r, sigma + 0.01, T, N, tipo, americana, q, fut)[0] - f0
    rho = crr(S0, K, r + 0.01, sigma, T, N, tipo, americana, q, fut)[0] - f0
    return {"precio": f0, "delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": rho}


def nodos_ejercicio(S0, K, r, sigma, T, N, q=0.0, fut=False):
    """Número de nodos de decisión (pasos 0..N-1) donde conviene ejercer la put americana."""
    if fut:
        q = r
    dt = T / N
    u = exp(sigma * sqrt(dt))
    d = 1 / u
    p = (exp((r - q) * dt) - d) / (u - d)
    disc = exp(-r * dt)
    V = np.maximum(K - S0 * u ** (N - np.arange(N + 1)) * d ** np.arange(N + 1), 0.0)
    n = 0
    for i in range(N - 1, -1, -1):
        k = np.arange(i + 1)
        cont = disc * (p * V[: i + 1] + (1 - p) * V[1 : i + 2])
        ej = np.maximum(K - S0 * u ** (i - k) * d**k, 0.0)
        n += int(np.sum((ej > cont) & (ej > 0)))
        V = np.maximum(cont, ej)
    return n


def frontera(S0, K, r, sigma, T, N=300, q=0.0, fut=False):
    """Precio crítico por día: máximo S donde conviene ejercer (None si no hay)."""
    if fut:
        q = r
    dt = T / N
    u = exp(sigma * sqrt(dt))
    d = 1 / u
    p = (exp((r - q) * dt) - d) / (u - d)
    disc = exp(-r * dt)
    V = np.maximum(K - S0 * u ** (N - np.arange(N + 1)) * d ** np.arange(N + 1), 0.0)
    out = {}
    for i in range(N - 1, -1, -1):
        k = np.arange(i + 1)
        Si = S0 * u ** (i - k) * d**k
        cont = disc * (p * V[: i + 1] + (1 - p) * V[1 : i + 2])
        ej = np.maximum(K - Si, 0.0)
        mask = (ej > cont) & (ej > 0)
        out[i] = float(Si[mask].max()) if mask.any() else None
        V = np.maximum(cont, ej)
    return [{"dias": 365 * T * i / N, "S_sobre_K": (out[i] / K) if out[i] else None} for i in range(0, N, 10)]


def curvas(S0, K, r, sigma, T, q=0.0, fut=False, n=41):
    """Put americana, europea, valor intrínseco y delta según el precio del subyacente (como las gráficas del Rmd)."""
    w = min(0.6, K * sigma * sqrt(T) * 5 / K)
    w_delta = min(0.5, 4 * sigma * sqrt(T))
    Sg = [(1 - w) * K + (2 * w * K) * i / (n - 1) for i in range(n)]
    am = [crr(s, K, r, sigma, T, 200, "put", True, q, fut)[0] for s in Sg]
    eu = [crr(s, K, r, sigma, T, 200, "put", False, q, fut)[0] for s in Sg]
    Sd = [(1 - w_delta) * K + (2 * w_delta * K) * i / (n - 1) for i in range(n)]
    dl = [griegas(s, K, r, sigma, T, 300, "put", True, q, fut)["delta"] for s in Sd]
    return {"S": Sg, "americana": am, "europea": eu, "intrinseco": [max(K - s, 0.0) for s in Sg], "S_delta": Sd, "delta": dl}


def prima_vs_tasa(S0, K, sigma, T, q=0.0, fut=False):
    """Prima de ejercicio anticipado (% de la put europea) para tasas de 0 % a 8 %."""
    out = []
    for r in [i / 100 for i in range(0, 9)]:
        am = crr(S0, K, r, sigma, T, 300, "put", True, q, fut)[0]
        eu = crr(S0, K, r, sigma, T, 300, "put", False, q, fut)[0]
        out.append({"r": r, "prima_pct": (am - eu) / eu})
    return out


def calcular() -> dict:
    activos = []
    for nombre, S0, K, cb, ca, pb, pa, iv_plat, fut in MERCADO:
        q = R if fut else 0.0
        call_mid, put_mid = (cb + ca) / 2, (pb + pa) / 2
        iv_put = iv_arbol(put_mid, S0, K, R, T, "put", fut)
        iv_call = iv_arbol(call_mid, S0, K, R, T, "call", fut)
        g = griegas(S0, K, R, iv_put, T, 500, "put", True, q, fut)
        pasos = [5, 10, 20, 50, 100, 200, 500, 1000]
        conv = [{"N": n, "americana": crr(S0, K, R, iv_put, T, n, "put", True, q, fut)[0],
                 "europea": crr(S0, K, R, iv_put, T, n, "put", False, q, fut)[0], "bs": bs_put(S0, K, R, iv_put, T, q)} for n in pasos]
        fin = conv[-1]
        activos.append({
            "activo": nombre, "S0": S0, "K": K, "futuro": fut,
            "call_mid": call_mid, "put_mid": put_mid, "iv_plataforma": iv_plat / 100,
            "iv_call": iv_call, "iv_put": iv_put,
            "paridad_obs": call_mid - put_mid, "paridad_teo": S0 * exp(-q * T) - K * exp(-R * T),
            "griegas": g,
            "griegas_rel": {"prima_sobre_spot": g["precio"] / S0, "gamma_x_S_100": g["gamma"] * S0 / 100,
                            "theta_sobre_prima": g["theta"] / g["precio"], "vega_sobre_prima": g["vega"] / g["precio"]},
            "convergencia": conv,
            "prima_ejercicio_pct": (fin["americana"] - fin["europea"]) / fin["europea"],
            "valor_temporal_pct_spot": (fin["americana"] - max(K - S0, 0)) / S0,
            "nodos_ejercicio_4_pasos": nodos_ejercicio(S0, K, R, iv_put, T, 4, q, fut),
            "frontera": frontera(S0, K, R, iv_put, T, 300, q, fut),
            "curvas": curvas(S0, K, R, iv_put, T, q, fut),
            "prima_vs_tasa": prima_vs_tasa(S0, K, iv_put, T, q, fut),
        })
    hull_am = crr(50, 52, 0.05, 0.30, 2, 2, "put", True)[0]
    hull_eu = crr(50, 52, 0.05, 0.30, 2, 2, "put", False)[0]
    return {
        "fecha_datos": "2026-10-21", "vencimiento": "2026-11-20", "r": R, "T_dias": 30,
        "fuente": "Capturas de la cadena de opciones (TradingView) del 21-oct-2026; r = rendimiento del Tesoro a 10 años (CNBC).",
        "estado": "dato transcrito de pantalla / calculado",
        "hull": {"S0": 50, "K": 52, "r": 0.05, "sigma": 0.30, "T": 2, "americana": hull_am, "europea": hull_eu},
        "activos": activos,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--docs", default="docs/data")
    a = ap.parse_args()
    d = calcular()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ruta = out / "arboles.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy(ruta, docs / "arboles.json")
    print("Escrito", ruta)


if __name__ == "__main__":
    main()
