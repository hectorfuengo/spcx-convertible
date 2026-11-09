# spcx-convertible

Dashboard de valuación de un bono convertible de SPCX: datos de LSEG/Refinitiv, Black-Scholes, cobertura con call spread y escenarios.

## Estructura

| Carpeta | Contenido |
|---|---|
| `data/raw/` | Exportes de Refinitiv tal cual, con la fecha en el nombre (`2026-10-21_bonos.csv`). **No se suben a GitHub** (licencia LSEG). |
| `data/inputs.csv` | Supuestos y datos, cada uno con fuente, fecha y estado (dato / supuesto del caso / supuesto del equipo). |
| `data/processed/` | Archivos JSON que consume el sitio (los genera Python). |
| `src/` | Cálculos en Python: `bs.py` (Black-Scholes), `bono.py` (bono simple y cupón de equilibrio), `ingesta.py` (exportes → JSON), `valuacion.py` (valuación del convertible), `cobertura.py` (note hedge, warrants y escenarios), `analisis.py` (razones financieras, estructura de deuda y comparables), `griegas.py` (griegas de las opciones listadas y del convertible con su cobertura). |
| `tests/` | Pruebas de los cálculos. |
| `notebooks/` | Notebooks de Colab con resultados parciales. |
| `docs/` | El sitio web (`index.html`) y los JSON que lee (`docs/data/`). |
| `reports/` | Reportes en Word/PDF y Excel de respaldo. |

## Cómo correr las pruebas

```bash
pip install -r requirements.txt
pytest
```

## Flujo de datos

1. Exportar desde Refinitiv a Excel, sin editar, con la fecha al inicio del nombre (`2026-10-26_bonos.xlsx`).
2. Guardar en `data/raw/` (solo local, no se sube).
3. Correr `python3 -m src.ingesta` (usa el archivo más reciente de cada tema). Genera `data/processed/*.json`; `resumen_mercado.json` trae los valores clave con fuente, fecha y estado.
4. Correr `python3 -m src.valuacion`: calcula la valuación (prima 25%, plazo 6 años por defecto; `--prima`, `--plazo`) con `data/opciones_iv.csv` y `data/opciones_tradingview.csv`, y escribe `data/processed/valuacion.json`.
5. Correr `python3 -m src.cobertura` (`--emision` en millones de USD, `--prima-warrant`): note hedge, warrants y escenarios al vencimiento. Escribe `data/processed/cobertura.json`. Ambos pasos copian a `docs/data/` los JSON que lee el sitio.
6. Correr `python3 -m src.analisis`: razones financieras, estructura de deuda (muro de vencimientos) y comparables. Escribe `data/processed/analisis.json` y lo copia a `docs/data/`.
7. Correr `python3 -m src.griegas`: lee `data/opciones_refinitiv_griegas.csv` (capturas de pantalla de LSEG, con fecha y fuente) y escribe `data/processed/griegas.json`, copiado a `docs/data/`.
8. Correr `python3 -m src.arboles`: árbol binomial CRR para las puts americanas de la tarea (SPCX, TSLA, MU, SPY, NQ); replica el R Markdown de la clase. Escribe `data/processed/arboles.json`.
9. Correr `python3 -m src.competidores`: indicadores, precios base 100 y correlación de SPCX contra RKLB, AVAV, KTOS, NOC, GD y BA (corte 2026-10-26). Escribe `competidores.json`.
10. Correr `python3 -m src.dashboard`: arma `docs/index.html` autocontenido desde `docs/index.src.html`, los JSON y las herramientas de la tarea en `docs/tools/` (árboles y GARCH). Los datos de la empresa están en `data/empresa.json`.
11. Correr `python3 -m src.swaps` antes del paso 10: swaps con Boeing (cap. 7 de Hull) a partir del cuaderno de Colab: swap de tasas, ventaja comparativa, swap de divisas, equity swaps sobre BA contra tasa, SPY e ITA, y cobertura. Lee `data/raw/precios_swaps.csv` (cierres de BA, SPY e ITA de Yahoo, que baja `descargar_precios_swaps.py`) y escribe `data/processed/swaps.json`. Incluye bonos y estructura de deuda de RTX (TradingView y Refinitiv) como contraparte real de la ventaja comparativa, y la curva MXN IRS de LSEG para descontar el swap de divisas. Siguen siendo supuestos el spot USD/MXN (falta el real), los cupones del swap de divisas y los márgenes variables de Boeing y RTX.
6. Revisar, hacer commit de `data/processed/`, `docs/data/` y `data/opciones_iv.csv`, y push. GitHub Pages publica `docs/`.

Opciones: `--raw`, `--out`, `--fecha YYYY-MM-DD` (fecha de valuación).

## Nota sobre los datos

Los exportes de LSEG/Refinitiv están sujetos a su licencia y por eso `data/raw/` está en `.gitignore`. El historial de SPCX empieza en su fecha de listado, por lo que habrá menos de 3 años de precios.

## Pendientes

- Pendientes de datos: CDS de SPCX; superficie de volatilidad completa (las IV actuales se transcribieron de pantalla); la cuenta de LSEG no permite exportar derivados.
- Confirmar que la licencia de LSEG permite publicar cifras derivadas en `data/processed/`.
- Menús y gráficas del sitio.


## Verificación contra fuentes primarias

`tests/test_deuda_10q.py` concilia la deuda de Refinitiv con la nota 9 del 10-Q al 30-sep-2026 (total, corto y largo plazo, SpaceX Notes y cupón ponderado) y los segmentos del 3T-2026 con el ingreso de Refinitiv. Las facilidades de crédito de Refinitiv se marcan como vigentes, pagadas o sin confirmar según el 10-Q, y el muro de vencimientos solo cuenta las vigentes. SPCX no registra derivados en sus notas auditadas ni en el 10-Q; la sección de swaps usa a Boeing por esa razón. El dashboard está hecho en HTML con Chart.js, no con Plotly.
