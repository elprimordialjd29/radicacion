"""
Liquidación LMA — datos de las prefacturas de cápita del SIE
(Gestión de Sistema Financiero > Ordenes de Pago > Prefactura, Excel del ícono de la impresora).

Sin Playwright: lo usan el bot (liquidacion.py) para guardar lo descargado y el worker para armar
el JSON de la pestaña «Liquidación LMA».

Reglas del usuario:
  * Por contrato, mes y régimen vale SIEMPRE la última prefactura que lo trae (la de consecutivo más
    alto), aunque sea un ajuste hecho meses después (p. ej. marzo reliquidado en julio) o una «PRUEBA».
  * Los valores salen tal cual del Excel que baja la impresora (no se recalculan ni se redondean).
  * Una prefactura trae muchos contratos: cada Excel actualiza todos los contratos que trae.
  * Siempre los dos regímenes (subsidiado y contributivo).

Base de datos aparte (worker_datos/liquidacion.db): no toca historial.db de la radicación.
"""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "worker_datos" / "liquidacion.db"
CARPETA = BASE / "descargas" / "prefacturas"

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
         "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
         "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SEPT": 9,
         "OCT": 10, "NOV": 11, "DIC": 12}
NOMBRE_MES = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE",
              "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
# columnas fijas del Excel del SIE (el resto son los conceptos: cursos de vida, rutas o servicios)
FIJAS = {"NIT": "nit", "NOMBRE IPS": "ips", "MUNICIPIO": "municipio", "NUMERO CONTRATO": "contrato",
         "TOTAL": "total", "AFILIADOS": "afiliados"}
TOLERANCIA = 1.0   # pesos: TOTAL vs suma de conceptos (el SIE redondea el TOTAL)


def sin_tildes(s):
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()


# ------------------------------------------------------------------ base de datos
def abrir(ruta=DB):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=30)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS prefacturas(
            consecutivo INTEGER PRIMARY KEY, descripcion TEXT, fecha_ini TEXT, fecha_fin TEXT,
            anio INTEGER, mes INTEGER, regimen TEXT, aviso TEXT, columnas TEXT, n_filas INTEGER,
            vigente INTEGER DEFAULT 1, primera_vez TEXT, ultima_descarga TEXT, ultima_vista TEXT);
        CREATE TABLE IF NOT EXISTS prefactura_filas(
            consecutivo INTEGER, contrato TEXT, nit TEXT, ips TEXT, municipio TEXT,
            total REAL, afiliados REAL, conceptos TEXT, PRIMARY KEY (consecutivo, contrato));
        CREATE TABLE IF NOT EXISTS busquedas(
            contrato TEXT, consecutivo INTEGER, fecha TEXT, PRIMARY KEY (contrato, consecutivo));
        CREATE TABLE IF NOT EXISTS corridas(
            inicio TEXT PRIMARY KEY, fin TEXT, contratos INTEGER, consultados INTEGER, prefacturas INTEGER,
            descargadas INTEGER, errores TEXT, avisos TEXT, completa INTEGER);
    """)
    return con


# ------------------------------------------------------------------ periodo y régimen
def periodo(descripcion, fecha_ini="", fecha_fin=""):
    """(año, mes, régimen, aviso) de una prefactura.

    El mes sale del NOMBRE del mes en la descripción, porque las fechas a veces están mal
    («… SUBSIDIADO ABRIL 2026» con fechas de marzo); si la descripción no nombra un mes, se usa la
    fecha inicial. Régimen: SUBSIDIADO → RS, CONTRIBUTIVO → RC (también «RS»/«RC» sueltos)."""
    d = sin_tildes(descripcion)
    fi = re.match(r"\s*(\d{4})\D(\d{1,2})", str(fecha_ini or ""))
    a_fi, m_fi = (int(fi.group(1)), int(fi.group(2))) if fi else (None, None)
    avisos = []

    nombrados = []
    for pal in re.findall(r"[A-Z]+", d):
        m = MESES.get(pal)
        if m and m not in nombrados:
            nombrados.append(m)
    if len(nombrados) == 1:
        mes = nombrados[0]
    elif nombrados:
        mes = m_fi if m_fi in nombrados else nombrados[0]
        avisos.append("la descripción nombra varios meses (" + ", ".join(NOMBRE_MES[m] for m in nombrados) +
                      f"); se tomó {NOMBRE_MES[mes]}")
    else:
        mes = m_fi
        if mes is None:
            avisos.append("no se pudo saber el mes (ni la descripción ni la fecha inicial lo dicen)")
    if nombrados and m_fi and mes != m_fi:
        avisos.append(f"la descripción dice {NOMBRE_MES[mes]} pero la fecha inicial es {fecha_ini}; se tomó {NOMBRE_MES[mes]}")

    anios = re.findall(r"(?<!\d)(20\d{2})(?!\d)", d)
    anio = int(anios[0]) if anios else a_fi

    # tolera errores de digitación del SIE: «CONTRIBBUTIVO», «CONTRIBUTIBO», «SUBSIDADO»…
    rs = bool(re.search(r"SUBSI|\bRS\b", d))
    rc = bool(re.search(r"CONTRI|\bRC\b", d))
    regimen = "RS" if rs and not rc else "RC" if rc and not rs else ""
    if not regimen:
        avisos.append("la descripción nombra los dos regímenes" if rs and rc
                      else "la descripción no dice si es subsidiado o contributivo")
    return anio, mes, regimen, "; ".join(avisos)


# ------------------------------------------------------------------ Excel de la impresora
def num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s:
        return 0.0
    if "," in s and "." in s:          # 1.234.567,89
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:             # 12.818.852 (puntos de miles)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def leer_excel(ruta):
    """Lee «estadistica.xlsx» → (conceptos en el orden del Excel, {contrato: fila}, avisos).
    fila = {nit, ips, municipio, total, afiliados, conceptos: {nombre: valor}} con los valores tal cual."""
    from openpyxl import load_workbook
    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        idx, conceptos, filas, avisos, encabezado = {}, [], {}, [], False
        for r in ws.iter_rows(values_only=True):
            if not encabezado:
                nombres = [sin_tildes(v) for v in r]
                if "NUMERO CONTRATO" in nombres:
                    encabezado = True
                    for i, n in enumerate(nombres):
                        if n in FIJAS and FIJAS[n] not in idx:
                            idx[FIJAS[n]] = i
                        elif n:
                            conceptos.append((i, " ".join(str(r[i]).split())))
                continue
            celda = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else None
            contrato = str(celda("contrato") or "").strip()
            if not contrato:
                continue
            fila = {"nit": str(celda("nit") or "").strip(), "ips": str(celda("ips") or "").strip(),
                    "municipio": str(celda("municipio") or "").strip(),
                    "total": num(celda("total")), "afiliados": num(celda("afiliados")),
                    "conceptos": {n: num(r[i]) for i, n in conceptos if i < len(r) and r[i] not in (None, "")}}
            if contrato in filas:      # el mismo contrato dos veces en una prefactura: se suman
                p = filas[contrato]
                avisos.append(f"el contrato {contrato} viene en varias filas; se sumaron")
                p["total"] += fila["total"]
                p["afiliados"] += fila["afiliados"]
                for k, v in fila["conceptos"].items():
                    p["conceptos"][k] = p["conceptos"].get(k, 0.0) + v
            else:
                filas[contrato] = fila
        if not encabezado:
            raise ValueError("el Excel no trae la columna NÚMERO CONTRATO")
        return [n for _, n in conceptos], filas, avisos
    finally:
        wb.close()


# ------------------------------------------------------------------ guardar
def registrar(con, consecutivo, descripcion, fecha_ini, fecha_fin, ahora):
    """La prefactura salió en una búsqueda: guarda o actualiza su descripción, fechas y periodo."""
    anio, mes, reg, aviso = periodo(descripcion, fecha_ini, fecha_fin)
    previo = con.execute("SELECT regimen, aviso FROM prefacturas WHERE consecutivo=?", (consecutivo,)).fetchone()
    if previo and not reg and previo[0]:
        reg, aviso = previo     # régimen deducido antes por los afiliados (la descripción no lo dice): se conserva
    if previo:
        con.execute("UPDATE prefacturas SET descripcion=?, fecha_ini=?, fecha_fin=?, anio=?, mes=?, regimen=?, aviso=?, "
                    "vigente=1, ultima_vista=? WHERE consecutivo=?",
                    (descripcion, fecha_ini, fecha_fin, anio, mes, reg, aviso, ahora, consecutivo))
    else:
        con.execute("INSERT INTO prefacturas (consecutivo, descripcion, fecha_ini, fecha_fin, anio, mes, regimen, aviso, "
                    "vigente, primera_vez, ultima_vista) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                    (consecutivo, descripcion, fecha_ini, fecha_fin, anio, mes, reg, aviso, ahora, ahora))


def guardar_excel(con, consecutivo, conceptos, filas, ahora):
    """Reemplaza las filas de la prefactura con lo que trae su Excel recién descargado."""
    con.execute("UPDATE prefacturas SET columnas=?, n_filas=?, ultima_descarga=? WHERE consecutivo=?",
                (json.dumps(conceptos, ensure_ascii=False), len(filas), ahora, consecutivo))
    con.execute("DELETE FROM prefactura_filas WHERE consecutivo=?", (consecutivo,))
    con.executemany("INSERT INTO prefactura_filas VALUES (?,?,?,?,?,?,?,?)",
                    [(consecutivo, c, f["nit"], f["ips"], f["municipio"], f["total"], f["afiliados"],
                      json.dumps(f["conceptos"], ensure_ascii=False)) for c, f in filas.items()])


def deducir_regimenes(con):
    """Prefacturas cuya descripción no dice el régimen (p. ej. «PRUEBA MARZO PMS-20001-2026-7 …»): se deduce
    comparando los afiliados de cada contrato con los de las prefacturas del mismo mes que sí lo dicen
    (subsidiado y contributivo difieren mucho en afiliados). Solo si todos los contratos apuntan al mismo
    régimen, cerca (≤ 15 %) de ese y lejos (≥ 50 %) del otro. Devuelve los avisos."""
    avisos = []
    sin = con.execute("SELECT consecutivo, anio, mes, descripcion FROM prefacturas "
                      "WHERE COALESCE(regimen,'')='' AND mes IS NOT NULL").fetchall()
    for k, anio, mes, desc in sin:
        votos, n = set(), 0
        for contrato, af in con.execute("SELECT contrato, afiliados FROM prefactura_filas WHERE consecutivo=?", (k,)).fetchall():
            dist = {}
            for rg, af2 in con.execute(
                    "SELECT p.regimen, f.afiliados FROM prefactura_filas f JOIN prefacturas p ON p.consecutivo=f.consecutivo "
                    "WHERE f.contrato=? AND p.anio=? AND p.mes=? AND p.regimen IN ('RS','RC') AND p.consecutivo<>?",
                    (contrato, anio, mes, k)):
                d = abs((af or 0) - (af2 or 0)) / max(af or 0, af2 or 0, 1)
                dist[rg] = min(d, dist.get(rg, 9))
            if not dist:
                continue
            rg = min(dist, key=dist.get)
            otro = dist.get("RC" if rg == "RS" else "RS", 9)
            votos.add(rg if dist[rg] <= 0.15 and otro >= 0.5 else "?")
            n += 1
        if n and len(votos) == 1 and "?" not in votos:
            rg = votos.pop()
            nota = (f"la descripción no dice el régimen; por los afiliados de sus {n} contrato(s) es "
                    f"{'subsidiado' if rg == 'RS' else 'contributivo'}")
            con.execute("UPDATE prefacturas SET regimen=?, aviso=? WHERE consecutivo=?", (rg, nota, k))
            avisos.append(f"Prefactura {k} «{desc}»: {nota}.")
    return avisos


def guardar_busqueda(con, contrato, consecutivos, ahora):
    con.execute("DELETE FROM busquedas WHERE contrato=?", (contrato,))
    con.executemany("INSERT OR IGNORE INTO busquedas VALUES (?,?,?)", [(contrato, k, ahora) for k in consecutivos])


def marcar_vigentes(con, vistos):
    """Solo tras una corrida completa (todos los contratos consultados sin error): la prefactura que ya no
    sale en ninguna búsqueda (se anuló o se reversó en el SIE) deja de contarse."""
    con.execute("UPDATE prefacturas SET vigente=0")
    con.executemany("UPDATE prefacturas SET vigente=1 WHERE consecutivo=?", [(k,) for k in vistos])


def registrar_corrida(con, inicio, fin, contratos, consultados, prefacturas, descargadas, errores, avisos, completa):
    con.execute("INSERT OR REPLACE INTO corridas VALUES (?,?,?,?,?,?,?,?,?)",
                (inicio, fin, contratos, consultados, prefacturas, descargadas,
                 json.dumps(errores, ensure_ascii=False), json.dumps(avisos[:300], ensure_ascii=False), int(completa)))
    # se guardan las últimas 60 corridas
    con.execute("DELETE FROM corridas WHERE inicio NOT IN (SELECT inicio FROM corridas ORDER BY inicio DESC LIMIT 60)")


# ------------------------------------------------------------------ validación
def validar(con, listados, descargadas, catalogo=None):
    """Avisos para revisar a mano: TOTAL ≠ suma de conceptos, prefactura que sale al buscar un contrato
    pero cuyo Excel no lo trae, y prefacturas sin mes o régimen claros."""
    avisos = []
    cat = set(catalogo or [])
    for contrato, lst in listados.items():
        for k in lst:
            if k in descargadas and not con.execute(
                    "SELECT 1 FROM prefactura_filas WHERE consecutivo=? AND contrato=?", (k, contrato)).fetchone():
                avisos.append(f"La prefactura {k} sale al buscar {contrato}, pero su Excel no trae ese contrato.")
    for k in sorted(descargadas):
        for contrato, total, conceptos in con.execute(
                "SELECT contrato, total, conceptos FROM prefactura_filas WHERE consecutivo=?", (k,)):
            if cat and contrato not in cat:
                continue
            suma = sum(json.loads(conceptos or "{}").values())
            # algunos contratos (p. ej. asistenciales) vienen solo con el TOTAL, sin detalle: eso no es error
            if suma and abs((total or 0) - suma) > TOLERANCIA:
                avisos.append(f"Prefactura {k}, contrato {contrato}: TOTAL {total:,.0f} y la suma de los conceptos "
                              f"{suma:,.2f} no coinciden.")
    for k, desc, aviso in con.execute("SELECT consecutivo, descripcion, aviso FROM prefacturas WHERE aviso<>'' AND vigente=1 "
                                      "ORDER BY consecutivo"):
        if k in descargadas or not descargadas:
            avisos.append(f"Prefactura {k} «{desc}»: {aviso}.")
    return avisos


# ------------------------------------------------------------------ JSON para la pestaña
def armar(con, catalogo, anio):
    """Por contrato (del listado), régimen y mes: la última prefactura que lo trae, con sus valores tal cual del
    Excel y las liquidaciones anteriores de ese mes (las que reemplazó)."""
    cat = {c["contrato"]: c for c in catalogo}
    prefs = {}
    for r in con.execute("SELECT consecutivo, descripcion, fecha_ini, fecha_fin, anio, mes, regimen, aviso, columnas, "
                         "n_filas, vigente, primera_vez, ultima_descarga FROM prefacturas WHERE anio=?", (anio,)):
        prefs[r[0]] = r
    grupos = {}     # (contrato, régimen, mes) → filas de la más nueva a la más vieja
    nuestros = {}   # consecutivo → [contratos del listado, valor]
    for k, contrato, nit, ips, muni, total, afil, conceptos in con.execute(
            "SELECT f.consecutivo, f.contrato, f.nit, f.ips, f.municipio, f.total, f.afiliados, f.conceptos "
            "FROM prefactura_filas f JOIN prefacturas p ON p.consecutivo=f.consecutivo "
            "WHERE p.anio=? ORDER BY f.consecutivo DESC", (anio,)):
        if contrato not in cat:
            continue
        p = prefs[k]
        n = nuestros.setdefault(k, [0, 0.0])
        n[0] += 1
        n[1] += total or 0
        if not p[10] or not p[5] or p[6] not in ("RS", "RC"):
            continue   # no vigente, o sin mes / régimen: se lista en «Revisar», no se usa
        grupos.setdefault((contrato, p[6], p[5]), []).append((k, nit, ips, muni, total, afil, conceptos))

    # orden de los conceptos: el de los Excel de las prefacturas usadas, de la más nueva a la más vieja
    usadas = sorted({lst[0][0] for lst in grupos.values()}, reverse=True)
    conceptos, pos = [], {}
    for k in usadas:
        for nom in json.loads(prefs[k][8] or "[]"):
            if nom not in pos:
                pos[nom] = len(conceptos)
                conceptos.append(nom)

    liq, info, uso = {}, {}, {}
    for (contrato, rg, mes), lst in grupos.items():
        k, nit, ips, muni, total, afil, cjson = lst[0]
        cv = {}
        for nom, v in json.loads(cjson or "{}").items():
            if nom not in pos:
                pos[nom] = len(conceptos)
                conceptos.append(nom)
            if v:
                cv[str(pos[nom])] = v
        liq.setdefault(contrato, {}).setdefault(rg, {})[str(mes)] = {
            "p": k, "t": total, "af": afil, "c": cv, "prev": [[x[0], x[4], x[5]] for x in lst[1:]]}
        uso[k] = uso.get(k, 0) + 1
        if contrato not in info or k > info[contrato][3]:
            info[contrato] = [nit, ips, muni, k]

    ult = con.execute("SELECT inicio, fin, contratos, consultados, prefacturas, descargadas, errores, avisos, completa "
                      "FROM corridas ORDER BY inicio DESC LIMIT 1").fetchone()
    corrida = None
    if ult:
        previa = con.execute("SELECT 1 FROM corridas WHERE inicio<? LIMIT 1", (ult[0],)).fetchone()
        corrida = {"inicio": ult[0], "fin": ult[1], "contratos": ult[2], "consultados": ult[3], "prefacturas": ult[4],
                   "descargadas": ult[5], "errores": json.loads(ult[6] or "{}"), "avisos": json.loads(ult[7] or "[]"),
                   "completa": bool(ult[8]), "primera": not previa,
                   "nuevas": sorted((k for k, p in prefs.items() if (p[11] or "") >= ult[0]), reverse=True)}
    return {
        "anio": anio,
        "corrida": corrida,
        "conceptos": conceptos,
        "pref": {str(k): {"d": p[1], "fi": p[2], "ff": p[3], "m": p[5], "r": p[6], "av": p[7] or "", "vig": int(p[10] or 0),
                          "n": nuestros.get(k, [0, 0])[0], "v": nuestros.get(k, [0, 0])[1], "uso": uso.get(k, 0),
                          "nuevo": p[11], "bajada": p[12]}
                 for k, p in sorted(prefs.items(), reverse=True) if k in nuestros or (p[7] or "")},
        "liq": liq,
        "info": {c: v[:3] for c, v in info.items()},
        "sin": sorted(c for c in cat if c not in liq),
    }
