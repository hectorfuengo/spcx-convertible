"""Black-Scholes para opciones europeas sin dividendos, con griegas.

Convenciones:
    S: precio spot            K: strike
    T: plazo en años          r: tasa libre de riesgo (continua, anual)
    sigma: volatilidad anual  (0.20 = 20%)

Unidades de las griegas:
    vega: cambio del precio por un cambio de 1.00 en sigma (divide entre 100 para 1 punto)
    theta: cambio por año (divide entre 365 para obtener por día)
    rho: cambio del precio por un cambio de 1.00 en r (divide entre 100 para 1 punto)
"""
from math import erf, exp, log, pi, sqrt


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("S, K, T y sigma deben ser positivos")
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    return d1, d1 - sigma * sqrt(T)


def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    return S * _cdf(d1) - K * exp(-r * T) * _cdf(d2)


def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    return K * exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def greeks(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> dict:
    """Devuelve delta, gamma, vega, theta y rho. kind: 'call' o 'put'."""
    if kind not in ("call", "put"):
        raise ValueError("kind debe ser 'call' o 'put'")
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    gamma = _pdf(d1) / (S * sigma * sqrt(T))
    vega = S * _pdf(d1) * sqrt(T)
    decay = -S * _pdf(d1) * sigma / (2.0 * sqrt(T))
    if kind == "call":
        delta = _cdf(d1)
        theta = decay - r * K * exp(-r * T) * _cdf(d2)
        rho = K * T * exp(-r * T) * _cdf(d2)
    else:
        delta = _cdf(d1) - 1.0
        theta = decay + r * K * exp(-r * T) * _cdf(-d2)
        rho = -K * T * exp(-r * T) * _cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}
