"""Pruebas de liquidacion_datos (sin SIE). Correr:  python bot/tests/test_liquidacion_datos.py
(o con pytest). La prueba del Excel necesita openpyxl (está en el venv del bot)."""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import liquidacion_datos as LD  # noqa: E402


def test_periodo_mes_de_la_descripcion():
    assert LD.periodo("LIQUIDACION CONTRATOS SEPTIEMBRE 2026 SUBSIDIADO PMS", "2026/09/01", "2026/09/30")[:3] == (2026, 9, "RS")
    assert LD.periodo("LIQUIDACION DE CONTRATOS CONTRIBUTIVO - MARZO 2026", "2026/03/01", "2026/03/31")[:3] == (2026, 3, "RC")
    # la descripción manda sobre las fechas (caso real: dice ABRIL con fechas de marzo)
    a, m, r, aviso = LD.periodo("LIQUIDACION DE CONTRATOS DNT-44001-2026-01 ASE-44001-2026-44 SUBSIDIADO ABRIL 2026",
                                "2026/03/01", "2026/03/31")
    assert (a, m, r) == (2026, 4, "RS") and "fecha inicial" in aviso
    # sin año en la descripción: el de la fecha inicial
    assert LD.periodo("LIQUIDACION CONTRATOS DUSAKAWI IPS ABRIL CONTRIBUTIVO PMS", "2026/04/01", "")[:3] == (2026, 4, "RC")
    # plurales, tildes y palabras truncadas
    assert LD.periodo("LIQUDACION DE CONTRATOS SUBSIDIADOS MARZO 2026", "2026/03/01", "")[:3] == (2026, 3, "RS")
    assert LD.periodo("LIQUIDACIÓN CAPITA CUARTA PARTE MARZO 2026 CONTRIBUTIV", "2026/03/01", "")[:3] == (2026, 3, "RC")
    # «MAYOR» no es mayo; sin mes en la descripción se usa la fecha inicial
    assert LD.periodo("CAPITA ADULTO MAYOR SUBSIDIADO", "2026/07/01", "")[1] == 7
    # las fechas pueden decir hasta noviembre: el mes es el de la descripción
    assert LD.periodo("PRUEBA CAPITA CONTRIBUTIVO JUNIO 2026 SIN PMS", "2026/06/01", "2026/11/30")[:3] == (2026, 6, "RC")


def test_periodo_avisos():
    assert "no dice si es subsidiado" in LD.periodo("LIQUIDACION MARZO 2026", "2026/03/01", "")[3]
    assert LD.periodo("LIQUIDACION MARZO 2026", "2026/03/01", "")[2] == ""
    assert "varios meses" in LD.periodo("AJUSTE MARZO EN JULIO 2026 SUBSIDIADO", "2026/07/01", "")[3]
    assert LD.periodo("AJUSTE MARZO EN JULIO 2026 SUBSIDIADO", "2026/07/01", "")[1] == 7   # la fecha decide entre los nombrados


def test_num():
    assert LD.num(1127387.0) == 1127387.0
    assert LD.num("1.234.567,89") == 1234567.89
    assert LD.num("$12.818.852") == 12818852.0      # puntos de miles
    assert LD.num("350148.42") == 350148.42
    assert LD.num(None) == 0.0 and LD.num("") == 0.0


def _bd():
    return LD.abrir(os.path.join(tempfile.mkdtemp(), "l.db"))


def _pref(con, k, desc, fi, filas, ahora="2026-11-26T10:00:00-05:00"):
    LD.registrar(con, k, desc, fi, fi, ahora)
    conceptos = ["PRIMERA INFANCIA 0 A 5 AÑOS", "VACUNACION"]
    LD.guardar_excel(con, k, conceptos, {c: {"nit": "1", "ips": "IPS " + c, "municipio": "RIOHACHA", "total": t,
                                             "afiliados": af, "conceptos": {"PRIMERA INFANCIA 0 A 5 AÑOS": t - 10, "VACUNACION": 10}}
                                         for c, (t, af) in filas.items()}, ahora)


def test_siempre_la_ultima_por_contrato_mes_y_regimen():
    con = _bd()
    _pref(con, 1647, "LIQUIDACION DE CONTRATOS SUBSIDIADO - MARZO 2026", "2026/03/01", {"PMS-1": (100, 5), "PMS-2": (200, 9)})
    _pref(con, 1648, "LIQUIDACION DE CONTRATOS CONTRIBUTIVO - MARZO 2026", "2026/03/01", {"PMS-1": (30, 1)})
    # ajuste de marzo hecho en julio (consecutivo más alto) que solo trae PMS-1
    _pref(con, 1716, "LIQUIDACION SUBSIDIADO MARZO 2026 AJUSTE", "2026/03/01", {"PMS-1": (150, 6)})
    # prueba posterior: también cuenta (siempre la última)
    _pref(con, 1888, "PRUEBA CAPITA SUBSIDIADO ABRIL 2026 PMS", "2026/04/01", {"PMS-2": (210, 9)})
    cat = [{"contrato": "PMS-1"}, {"contrato": "PMS-2"}, {"contrato": "ASB-9"}]
    j = LD.armar(con, cat, 2026)
    assert j["liq"]["PMS-1"]["RS"]["3"]["p"] == 1716 and j["liq"]["PMS-1"]["RS"]["3"]["t"] == 150
    assert j["liq"]["PMS-1"]["RS"]["3"]["prev"] == [[1647, 100, 5]]
    assert j["liq"]["PMS-2"]["RS"]["3"]["p"] == 1647          # el ajuste no traía PMS-2: sigue la 1647
    assert j["liq"]["PMS-1"]["RC"]["3"]["t"] == 30             # contributivo aparte
    assert j["liq"]["PMS-2"]["RS"]["4"]["p"] == 1888
    assert j["sin"] == ["ASB-9"]
    c = j["liq"]["PMS-1"]["RS"]["3"]["c"]
    assert sum(c.values()) == 150 and j["conceptos"][0] == "PRIMERA INFANCIA 0 A 5 AÑOS"
    assert j["pref"]["1716"]["uso"] == 1 and j["pref"]["1647"]["uso"] == 1


def test_prefactura_no_vigente_no_cuenta():
    con = _bd()
    _pref(con, 10, "LIQUIDACION SUBSIDIADO MAYO 2026", "2026/05/01", {"PMS-1": (100, 5)})
    _pref(con, 11, "LIQUIDACION SUBSIDIADO MAYO 2026 CORREGIDA", "2026/05/01", {"PMS-1": (120, 5)})
    LD.marcar_vigentes(con, {10})      # la 11 ya no sale en el SIE (se reversó)
    j = LD.armar(con, [{"contrato": "PMS-1"}], 2026)
    assert j["liq"]["PMS-1"]["RS"]["5"]["p"] == 10
    LD.registrar(con, 11, "LIQUIDACION SUBSIDIADO MAYO 2026 CORREGIDA", "2026/05/01", "", "2026-11-27T10:00:00-05:00")
    assert LD.armar(con, [{"contrato": "PMS-1"}], 2026)["liq"]["PMS-1"]["RS"]["5"]["p"] == 11   # volvió a salir


def test_validar():
    con = _bd()
    _pref(con, 20, "LIQUIDACION SUBSIDIADO JUNIO 2026", "2026/06/01", {"PMS-1": (100, 5)})
    con.execute("UPDATE prefactura_filas SET total=105 WHERE consecutivo=20")     # TOTAL ≠ suma de conceptos
    avisos = LD.validar(con, {"PMS-1": [20], "PMS-3": [20]}, {20}, ["PMS-1", "PMS-3"])
    assert any("PMS-3" in a and "no trae ese contrato" in a for a in avisos)
    assert any("no coinciden" in a for a in avisos)
    # sin detalle por concepto (solo TOTAL) no es error
    con.execute("UPDATE prefactura_filas SET conceptos='{}' WHERE consecutivo=20")
    assert not any("no coinciden" in a for a in LD.validar(con, {}, {20}, ["PMS-1"]))


def test_leer_excel():
    try:
        from openpyxl import Workbook
    except ImportError:
        print("  (sin openpyxl: se omite test_leer_excel)")
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "DATOS"
    ws.append(["NIT", "NOMBRE IPS", "MUNICIPIO", "NÚMERO CONTRATO", "TOTAL", "AFILIADOS", "PRIMERA INFANCIA 0 A 5 AÑOS",
               "VACUNACION", None, None])
    ws.append(["900", "IPS UNO", "RIOHACHA", "PMS-44001-2026-30", 1127387.0, 52.0, 9270.0, 57512.0])
    ws.append(["901", "IPS DOS", "MAICAO", "PMS-44430-2026-1", 10.0, 1.0, 4.0, 6.0])
    ws.append([None, None, None, None, None, None])
    ruta = os.path.join(tempfile.mkdtemp(), "estadistica.xlsx")
    wb.save(ruta)
    conceptos, filas, avisos = LD.leer_excel(ruta)
    assert conceptos == ["PRIMERA INFANCIA 0 A 5 AÑOS", "VACUNACION"]
    assert filas["PMS-44001-2026-30"]["total"] == 1127387.0 and filas["PMS-44001-2026-30"]["afiliados"] == 52.0
    assert filas["PMS-44001-2026-30"]["conceptos"]["VACUNACION"] == 57512.0
    assert len(filas) == 2 and not avisos


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for p in pruebas:
        p()
        print("ok", p.__name__)
    print(f"{len(pruebas)} pruebas bien")
