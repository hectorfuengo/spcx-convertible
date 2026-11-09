"""Descarga los precios que usa el cuaderno de swaps (BA, SPY, ITA y USD/MXN) y los guarda en un solo CSV.

Uso (en Colab o en tu computadora):
    pip install yfinance
    python descargar_precios_swaps.py
Genera precios_swaps.csv con cierres diarios ajustados de los últimos 2 años. Súbelo al chat.
"""
import pandas as pd
import yfinance as yf

TICKERS = {"BA": "BA", "SPY": "SPY", "ITA": "ITA", "USDMXN": "MXN=X"}
fin = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
inicio = fin - pd.DateOffset(years=2)

cierres = {}
for nombre, simbolo in TICKERS.items():
    s = yf.download(simbolo, start=inicio, end=fin, auto_adjust=True, progress=False, timeout=20)["Close"]
    s = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
    cierres[nombre] = s.dropna().astype(float)
    print(nombre, len(cierres[nombre]), "datos, último:", round(float(cierres[nombre].iloc[-1]), 4), cierres[nombre].index[-1].date())

df = pd.concat(cierres, axis=1)
df.index.name = "fecha"
df.to_csv("precios_swaps.csv")
print("Guardado precios_swaps.csv", df.shape)
