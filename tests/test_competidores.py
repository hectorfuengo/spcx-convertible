from src import competidores as c


def test_corr_perfecta_y_opuesta():
    assert abs(c._corr([1, 2, 3, 4], [2, 4, 6, 8]) - 1) < 1e-12
    assert abs(c._corr([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12


def test_retorno_y_drawdown():
    s = [("a", 100.0), ("b", 120.0), ("c", 60.0), ("d", 90.0)]
    assert abs(c._ret(s, 1) - 0.5) < 1e-12
    assert c._ret(s, 10) is None
    assert abs(c._max_dd(s) + 0.5) < 1e-12
