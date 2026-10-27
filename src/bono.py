"""Bono simple (cupones semestrales) y cupon de equilibrio de un convertible.

valor del convertible = valor del bono simple + valor de la opcion de conversion
"""


def valor_bono_simple(cupon: float, ytm: float, anios: float,
                      nominal: float = 1000.0, frecuencia: int = 2) -> dict:
    """Valor presente de un bono con cupon fijo.

    cupon: tasa anual del cupon (0.0193 = 1.93%)
    ytm: tasa de descuento anual (0.0575 = 5.75%), capitalizada con la misma frecuencia
    Devuelve el valor de los cupones, el del principal y el total.
    """
    n = round(anios * frecuencia)
    i = ytm / frecuencia
    pago = cupon * nominal / frecuencia
    cupones = sum(pago / (1 + i) ** k for k in range(1, n + 1))
    principal = nominal / (1 + i) ** n
    return {"cupones": cupones, "principal": principal, "total": cupones + principal}


def cupon_de_equilibrio(valor_objetivo: float, ytm: float, anios: float,
                        nominal: float = 1000.0, frecuencia: int = 2) -> float:
    """Cupon anual que hace que el bono simple valga `valor_objetivo`.

    Es lineal en el cupon, asi que se resuelve de forma exacta (sin iteraciones).
    """
    base = valor_bono_simple(0.0, ytm, anios, nominal, frecuencia)["total"]
    por_unidad = valor_bono_simple(1.0, ytm, anios, nominal, frecuencia)["total"] - base
    return (valor_objetivo - base) / por_unidad
