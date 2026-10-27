# spcx-convertible

Dashboard de valuación de un bono convertible de SPCX: datos de LSEG/Refinitiv, Black-Scholes, cobertura con call spread y escenarios.

## Estructura

| Carpeta | Contenido |
|---|---|
| `data/raw/` | Exportes de Refinitiv tal cual, con la fecha en el nombre (`2026-10-21_bonos.csv`). **No se suben a GitHub** (licencia LSEG). |
| `data/inputs.csv` | Supuestos y datos, cada uno con fuente, fecha y estado (dato / supuesto del caso / supuesto del equipo). |
| `data/processed/` | Archivos JSON que consume el sitio (los genera Python). |
| `src/` | Cálculos en Python (`bs.py`: Black-Scholes y griegas). |
| `tests/` | Pruebas de los cálculos. |
| `notebooks/` | Notebooks de Colab con resultados parciales. |
| `docs/` | El sitio web (HTML + JS + gráficas). |
| `reports/` | Reportes en Word/PDF y Excel de respaldo. |

## Cómo correr las pruebas

```bash
pip install -r requirements.txt
pytest
```

## Flujo de datos

1. Exportar desde Refinitiv a CSV/Excel, sin editar, con la fecha al inicio del nombre.
2. Guardar en `data/raw/` (solo local).
3. Un script convierte los exportes a `data/processed/`.
4. El sitio solo lee `data/processed/`.

## Nota sobre los datos

Los exportes de LSEG/Refinitiv están sujetos a su licencia y por eso `data/raw/` está en `.gitignore`. El historial de SPCX empieza en su fecha de listado, por lo que habrá menos de 3 años de precios.

## Pendientes

- Pruebas contra el caso Molson Coors (se agregan cuando se tengan los parámetros verificados del PDF).
- Cargar datos de SPCX y generar los JSON.
- Menús y gráficas del sitio.
