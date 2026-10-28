# spcx-convertible

Dashboard de valuación de un bono convertible de SPCX: datos de LSEG/Refinitiv, Black-Scholes, cobertura con call spread y escenarios.

## Estructura

| Carpeta | Contenido |
|---|---|
| `data/raw/` | Exportes de Refinitiv tal cual, con la fecha en el nombre (`2026-10-21_bonos.csv`). **No se suben a GitHub** (licencia LSEG). |
| `data/inputs.csv` | Supuestos y datos, cada uno con fuente, fecha y estado (dato / supuesto del caso / supuesto del equipo). |
| `data/processed/` | Archivos JSON que consume el sitio (los genera Python). |
| `src/` | Cálculos en Python: `bs.py` (Black-Scholes), `bono.py` (bono simple y cupón de equilibrio), `ingesta.py` (exportes → JSON), `valuacion.py` (valuación del convertible). |
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
4. Correr `python3 -m src.valuacion`: calcula la valuación (prima 25%, plazo 6 años por defecto; `--prima`, `--plazo`) con `data/opciones_iv.csv` y escribe `data/processed/valuacion.json`. También copia a `docs/data/` los JSON que lee el sitio.
5. Revisar, hacer commit de `data/processed/`, `docs/data/` y `data/opciones_iv.csv`, y push. GitHub Pages publica `docs/`.

Opciones: `--raw`, `--out`, `--fecha YYYY-MM-DD` (fecha de valuación).

## Nota sobre los datos

Los exportes de LSEG/Refinitiv están sujetos a su licencia y por eso `data/raw/` está en `.gitignore`. El historial de SPCX empieza en su fecha de listado, por lo que habrá menos de 3 años de precios.

## Pendientes

- Exportes faltantes: cadena de opciones y superficie de volatilidad, calificaciones y CDS de SPCX, precios de comparables a 5 años.
- Confirmar que la licencia de LSEG permite publicar cifras derivadas en `data/processed/`.
- Menús y gráficas del sitio.
