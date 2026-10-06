#!/usr/bin/env python3
"""
SIE Dusakawi — Bot de seguimiento de radicación (Cápita)

Flujo:
  1. Inicia sesión en el SIE (asdempleados.dusakawiepsi.com:8080/sie_dusakawi)
  2. Abre Gestión de Cuentas Médicas > Consulta Recepción
  3. Para cada contrato de contratos.txt: Tipo Régimen + Tipo Contrato Cápita +
     Estado = Radicado -> Buscar -> lee todos los registros de la tabla
  4. Filtra por los meses pedidos (Fecha Recepción), guarda Excel y compara
     con la corrida anterior para avisar qué se radicó nuevo.

Uso:
  python sie_bot.py enero febrero
  python sie_bot.py enero febrero --anio 2026 --regimen RS
  python sie_bot.py --todos            (sin filtro de mes)
  python sie_bot.py enero --oculto     (sin ver el navegador)
"""
import argparse
import getpass
import os
import re
import sqlite3
import subprocess
import sys
import json
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

import rips_json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = Path(__file__).resolve().parent
BASE_URL = "http://asdempleados.dusakawiepsi.com:8080/sie_dusakawi"
LOGIN_URL = f"{BASE_URL}/login.xhtml"
CONSULTA_URL = (f"{BASE_URL}/pages/audit/reception_consulta_support_rips/"
                "reception_consulta_support_rips.xhtml?SW_CREACION_EPS=1")

DESCARGAS = BASE / "descargas"
LOGS = BASE / "logs"
DB = BASE / "historial.db"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
NOMBRE_MES = {v: k.capitalize() for k, v in MESES.items() if k != "setiembre"}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def notificar(titulo, texto):
    """Notificación nativa de macOS (no falla si no se puede)."""
    if sys.platform != "darwin":
        return
    texto = texto.replace('"', "'")
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{texto}" with title "{titulo}"'],
                       check=False, capture_output=True)
    except Exception:
        pass


# ----------------------------------------------------------------- contratos
def cargar_contratos(ruta):
    """Devuelve (lista de contratos, {contrato: datos del listado}).
    Acepta el Excel CONTRATOS_CAPITADOS (MUNICIPIO, NIT, prestador, No. CONTRATO,
    INICIO, FIN, ESTADO DEL CONTRATO, VALOR CONTRATO) o un .txt con uno por línea."""
    ruta = Path(ruta).expanduser()
    if not ruta.exists():
        sys.exit(f"No existe el listado de contratos: {ruta}\n"
                 "Configura SIE_CONTRATOS en bot/.env con la ruta del Excel.")
    meta = {}
    if ruta.suffix.lower() == ".json":
        # [{"contrato": "...", "prestador": "...", "inicio": "YYYY-MM-DD", ...}, ...]
        filas = json.loads(ruta.read_text(encoding="utf-8"))
        valores = []
        for f in filas:
            c = str(f.get("contrato", "")).strip()
            if c:
                valores.append(c)
                meta[c] = {k: str(f.get(k) or "") for k in ("prestador", "nit", "municipio", "inicio",
                                                          "fin", "estado_contrato", "valor_contrato")}
    elif ruta.suffix.lower() in (".xlsx", ".xls", ".csv"):
        df = pd.read_csv(ruta, dtype=str) if ruta.suffix.lower() == ".csv" \
            else pd.read_excel(ruta, dtype=str)
        cols = [str(c) for c in df.columns]
        df.columns = cols
        c_con = next((c for c in cols if "contrat" in c.lower() and "estado" not in c.lower()
                      and "valor" not in c.lower()), cols[0])
        busca = lambda *k: next((c for c in cols if all(x in c.lower() for x in k)), None)
        c_nit = busca("nit")
        # el nombre del prestador viene en una columna sin título junto al NIT
        c_pre = busca("prestador") or busca("ips") or next(
            (c for c in cols if c.startswith("Unnamed") or not c.strip()), None)
        campos = {"prestador": c_pre, "nit": c_nit, "municipio": busca("municip"),
                  "inicio": busca("inicio"), "fin": busca("fin"),
                  "estado_contrato": busca("estado"), "valor_contrato": busca("valor", "contrato")}
        valores = []
        for _, r in df.iterrows():
            v = str(r[c_con]).strip() if pd.notna(r[c_con]) else ""
            if not v:
                continue
            valores.append(v)
            meta[v] = {k: (str(r[c]).strip() if c and pd.notna(r[c]) else "")
                       for k, c in campos.items()}
            for k in ("inicio", "fin"):
                meta[v][k] = meta[v][k][:10]
    else:
        valores = ruta.read_text(encoding="utf-8").splitlines()
    vistos, lista = set(), []
    for v in valores:
        v = str(v).strip()
        if v and not v.startswith("#") and v not in vistos:
            vistos.add(v)
            lista.append(v)
    return lista, meta


def vigente_en(meta, anio, meses):
    """True si el contrato está vigente en al menos uno de los meses pedidos."""
    if not meses or not meta.get("inicio"):
        return True
    ini = pd.to_datetime(meta.get("inicio"), errors="coerce")
    fin = pd.to_datetime(meta.get("fin") or f"{anio}-12-31", errors="coerce")
    for m in meses:
        p_ini = pd.Timestamp(anio, m, 1)
        p_fin = p_ini + pd.offsets.MonthEnd(0)
        if (pd.isna(ini) or ini <= p_fin) and (pd.isna(fin) or fin >= p_ini):
            return True
    return False


def parsear_meses(tokens):
    meses = []
    for t in tokens:
        t = t.strip().lower()
        if t.isdigit() and 1 <= int(t) <= 12:
            meses.append(int(t))
        elif t in MESES:
            meses.append(MESES[t])
        else:
            sys.exit(f"Mes no reconocido: {t}")
    return sorted(set(meses))


# ------------------------------------------------------------ helpers de UI
def esperar_ajax(page, timeout=60000):
    """Espera a que PrimeFaces/jQuery terminen sus peticiones AJAX."""
    try:
        page.wait_for_function(
            """() => {
                const pfOk = !window.PrimeFaces || !PrimeFaces.ajax ||
                             PrimeFaces.ajax.Queue.isEmpty();
                const jqOk = !window.jQuery || jQuery.active === 0;
                return pfOk && jqOk;
            }""", timeout=timeout)
    except PWTimeout:
        log("  (aviso) el servidor tardó demasiado en responder")
    page.wait_for_timeout(400)


def xp_label(texto):
    # primer elemento visible cuyo texto propio es exactamente `texto`
    return f"(//*[not(self::script) and not(self::th) and normalize-space(text())='{texto}'])[1]"


def campo_texto(page, label):
    return page.locator(
        f"xpath={xp_label(label)}/following::input[not(@type='hidden')][1]")


def menu_de(page, label):
    return page.locator(
        f"xpath={xp_label(label)}/following::div[contains(concat(' ',normalize-space(@class),' '),' ui-selectonemenu ')][1]")


def valor_menu(page, label):
    try:
        return menu_de(page, label).locator(".ui-selectonemenu-label").inner_text(timeout=3000).strip()
    except Exception:
        return ""


def elegir_menu(page, label, deseado):
    """Selecciona en un selectOneMenu de PrimeFaces. Coincidencia exacta y,
    si no hay, la primera opción que CONTIENE el texto (sin tildes/mayúsculas)."""
    menu = menu_de(page, label)
    menu.wait_for(state="visible", timeout=20000)
    menu_id = menu.get_attribute("id")
    menu.click()
    panel = page.locator(f"[id='{menu_id}_panel']")
    panel.wait_for(state="visible", timeout=10000)
    items = panel.locator("li.ui-selectonemenu-item")
    textos = [t.strip() for t in items.all_inner_texts()]

    def norm(s):
        s = s.lower()
        for a, b in zip("áéíóú", "aeiou"):
            s = s.replace(a, b)
        return s.strip()

    idx = next((i for i, t in enumerate(textos) if norm(t) == norm(deseado)), None)
    if idx is None:
        idx = next((i for i, t in enumerate(textos) if norm(deseado) in norm(t)), None)
    if idx is None:
        page.keyboard.press("Escape")
        raise RuntimeError(f"'{deseado}' no está en '{label}'. Opciones: {textos}")
    items.nth(idx).click()
    esperar_ajax(page)
    return textos[idx]


def evidencia(page, nombre):
    """Guarda captura + HTML para diagnosticar fallos."""
    LOGS.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        page.screenshot(path=str(LOGS / f"{marca}_{nombre}.png"), full_page=True)
        (LOGS / f"{marca}_{nombre}.html").write_text(page.content(), encoding="utf-8")
        log(f"  evidencia guardada en logs/{marca}_{nombre}.png")
    except Exception:
        pass


# --------------------------------------------------------------- navegación
def iniciar_sesion(page, usuario, clave, anio):
    log("Abriendo login del SIE…")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.locator("xpath=//label[normalize-space()='Usuario']/following::input[1]").fill(usuario)
    page.locator("input[type=password]").fill(clave)
    anio_in = page.locator("xpath=//label[normalize-space()='Año Trabajo']/following::input[1]")
    if anio_in.count():
        anio_in.fill(str(anio))
    page.get_by_role("button", name="Ingresar").click()
    try:
        page.wait_for_url(re.compile(r"home\.xhtml|index\.xhtml"), timeout=30000)
    except PWTimeout:
        if "login" in page.url:
            evidencia(page, "login_fallido")
            sys.exit("No se pudo iniciar sesión. Revisa usuario/clave en el archivo .env")
    log("Sesión iniciada ✔")


def abrir_consulta(page):
    log("Abriendo Consulta Recepción…")
    page.goto(CONSULTA_URL, wait_until="domcontentloaded")
    esperar_ajax(page)
    if page.locator(f"xpath={xp_label('Número Contrato Prestador')}").count() == 0:
        # Plan B: entrar por el menú como lo haría una persona
        log("  entrando por el menú Gestión de Cuentas Médicas…")
        page.goto(f"{BASE_URL}/medical_accounts.xhtml?URL_ANTERIOR=medical_accounts",
                  wait_until="domcontentloaded")
        page.get_by_text("Consulta Recepción", exact=True).first.click()
        page.wait_for_load_state("domcontentloaded")
        esperar_ajax(page)
    campo_texto(page, "Número Contrato Prestador").wait_for(state="visible", timeout=30000)
    log("Consulta Recepción lista ✔")


def configurar_filtros(page, regimen, tipo_contrato, estado, cantidad):
    """Pone Tipo Régimen, Tipo Contrato, Estado y Cantidad (solo si cambiaron)."""
    if regimen and valor_menu(page, "Tipo Régimen").lower() != regimen.lower():
        log(f"  Tipo Régimen → {elegir_menu(page, 'Tipo Régimen', regimen)}")
    if tipo_contrato.lower() not in valor_menu(page, "Tipo Contrato").lower():
        log(f"  Tipo Contrato → {elegir_menu(page, 'Tipo Contrato', tipo_contrato)}")
    if estado.lower() not in valor_menu(page, "Estado").lower():
        log(f"  Estado → {elegir_menu(page, 'Estado', estado)}")
    cant = campo_texto(page, "Cantidad")
    if cant.count() and cant.input_value() != str(cantidad):
        cant.fill(str(cantidad))


LEER_TABLA_JS = r"""
() => {
  const tablas = [...document.querySelectorAll('.ui-datatable')];
  const dt = tablas.find(t => [...t.querySelectorAll('thead th')]
                     .some(th => th.innerText.trim() === 'Estado'));
  if (!dt) return {headers: [], rows: [], next: false};
  const headers = [...dt.querySelectorAll('thead th')]
                    .map(th => th.innerText.replace(/\s+/g, ' ').trim());
  const rows = [...dt.querySelectorAll('tbody > tr')]
     .filter(tr => !tr.classList.contains('ui-datatable-empty-message'))
     .map(tr => [...tr.children].map(td => td.innerText.replace(/\s+/g, ' ').trim()));
  const nx = dt.querySelector('.ui-paginator-next');
  const next = !!nx && !nx.classList.contains('ui-state-disabled');
  return {headers, rows, next};
}
"""


# Columna (0 = primera) del ícono "hoja" que descarga el soporte de RIPS,
# el que está justo después del ojo.
COL_SOPORTE = 3
SOPORTES = DESCARGAS / "soportes"


def limpiar_nombre(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(s)).strip("_") or "sin_nombre"


def descargar_soporte(page, fila, contrato, recepcion):
    """Clic en la hojita de la fila y guarda el archivo. Si ya se descargó
    antes, reutiliza el archivo (no vuelve a bajarlo)."""
    carpeta = SOPORTES / limpiar_nombre(contrato)
    carpeta.mkdir(parents=True, exist_ok=True)
    previos = list(carpeta.glob(f"{limpiar_nombre(recepcion)}__*"))
    if previos:
        return previos[0]
    boton = fila.locator('button[title*="soporte de Rips"]').first
    if not boton.count():  # respaldo: 4ª columna de íconos
        boton = fila.locator("td").nth(COL_SOPORTE).locator("a, button").first
    with page.expect_download(timeout=90000) as dl:
        boton.click()
    d = dl.value
    destino = carpeta / f"{limpiar_nombre(recepcion)}__{limpiar_nombre(d.suggested_filename)}"
    d.save_as(str(destino))
    esperar_ajax(page)
    return destino


def leer_textos(ruta):
    """Devuelve el texto del soporte (soporta .txt o .zip con varios archivos)."""
    ruta = Path(ruta)
    datos = []
    if zipfile.is_zipfile(ruta):
        with zipfile.ZipFile(ruta) as z:
            datos = [z.read(n) for n in z.namelist() if not n.endswith("/")]
    else:
        datos = [ruta.read_bytes()]
    textos = []
    for b in datos:
        for enc in ("utf-8", "latin-1"):
            try:
                textos.append(b.decode(enc))
                break
            except UnicodeDecodeError:
                continue
    return "\n".join(textos)


RE_FECHA = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def periodo_soporte(ruta):
    """Saca el periodo de atención de la sección ARCHIVO-CONSULTAS.
    Si no hay consultas, usa las fechas de los demás servicios.
    Nunca usa USUARIOS (fechas de nacimiento) ni FACTURAS."""
    secciones = rips_json.leer_plano(leer_textos(ruta))

    def fechas_de(lineas):
        return [(int(a), int(m), int(d)) for l in lineas for a, m, d in RE_FECHA.findall(l)]

    fuente = "CONSULTAS"
    fechas = fechas_de(secciones.get("CONSULTAS", []))
    if not fechas:
        fuente = "OTROS SERVICIOS"
        fechas = fechas_de([l for k, v in secciones.items()
                            if k not in ("FACTURAS", "USUARIOS", "CONSULTAS") for l in v])
    if not fechas:
        return {"Periodo Año": None, "Periodo Mes N": None, "Fecha atención mín": "",
                "Fecha atención máx": "", "Nº registros con fecha": 0, "Fuente periodo": "SIN FECHAS"}
    conteo = Counter((a, m) for a, m, _ in fechas)
    (anio, mes), _ = conteo.most_common(1)[0]
    fmt = lambda f: f"{f[0]:04d}-{f[1]:02d}-{f[2]:02d}"
    return {"Periodo Año": anio, "Periodo Mes N": mes,
            "Fecha atención mín": fmt(min(fechas)), "Fecha atención máx": fmt(max(fechas)),
            "Nº registros con fecha": len(fechas),
            "Fuente periodo": fuente + (" (varios meses)" if len(conteo) > 1 else "")}


def buscar_contrato(page, contrato, con_soportes=True, regimen=""):
    campo = campo_texto(page, "Número Contrato Prestador")
    campo.fill("")
    campo.fill(contrato)
    # OJO: la barra superior tiene otro botón "buscar" (cmdGeneralSearch) que abre un diálogo
    # de búsqueda en el menú; el de la consulta es #cmdBuscar dentro del formulario formMtto.
    boton = page.locator("#cmdBuscar")
    if not boton.count():
        boton = page.locator("form#formMtto button", has_text="Buscar").first
    boton.click()
    esperar_ajax(page)
    page.wait_for_timeout(800)

    tabla = page.locator(".ui-datatable").filter(
        has=page.locator("th", has_text="Estado")).first
    headers, filas, extras = [], [], []
    for _ in range(200):  # páginas
        data = page.evaluate(LEER_TABLA_JS)
        headers = data["headers"] or headers
        for i, r in enumerate(data["rows"]):
            filas.append(r)
            info = {}
            if con_soportes:
                # índice de "Recepción RIPS" para nombrar el archivo
                idx = next((k for k, h in enumerate(headers) if "recepci" in h.lower()
                            and "rips" in h.lower() and "usuario" not in h.lower()), None)
                recepcion = r[idx] if idx is not None and idx < len(r) else f"fila{len(filas)}"
                try:
                    ruta = descargar_soporte(page, tabla.locator("tbody > tr").nth(i),
                                             contrato, recepcion)
                    info = periodo_soporte(ruta)
                    info["Archivo soporte"] = str(ruta.relative_to(BASE))
                    log(f"    soporte {recepcion}: periodo "
                        f"{info['Periodo Mes N'] or '?'}/{info['Periodo Año'] or '?'}")
                except Exception as e:
                    info = {"Fuente periodo": "ERROR DESCARGA: " + str(e).splitlines()[0][:100]}
                    log(f"    soporte {recepcion}: no se pudo descargar")
            extras.append(info)
        if not data["next"]:
            break
        page.locator(".ui-datatable .ui-paginator-next").first.click()
        esperar_ajax(page)

    if not filas:
        return pd.DataFrame()
    n = max(len(r) for r in filas)
    headers = (headers + [""] * n)[:n]
    # columnas sin título = íconos de acción -> se descartan
    nombres = [h if h else f"_c{i}" for i, h in enumerate(headers)]
    df = pd.DataFrame([(r + [""] * n)[:n] for r in filas], columns=nombres)
    df = df[[c for c in df.columns if not c.startswith("_c")]]
    df.insert(0, "Contrato Consultado", contrato)
    df.insert(1, "Régimen", regimen)
    if con_soportes:
        df = pd.concat([df, pd.DataFrame(extras)], axis=1)
    return df


# ------------------------------------------------------------- procesamiento
def col(df, *claves):
    if len(claves) == 1:  # coincidencia exacta primero (evita que "ips" caiga en "Recepción RIPS")
        exacta = next((c for c in df.columns if c.strip().lower() == claves[0]), None)
        if exacta:
            return exacta
    for c in df.columns:
        lc = c.lower()
        if all(k in lc for k in claves):
            return c
    return None


def a_numero(v):
    s = re.sub(r"[^\d,.-]", "", str(v))
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".")  # formato $12.818.852
    try:
        return float(s)
    except ValueError:
        return 0.0


def preparar(df, por_soporte=True):
    """Año/Mes = periodo de atención sacado del soporte RIPS (ARCHIVO-CONSULTAS).
    Con --por-recepcion se usa la Fecha Recepción del SIE."""
    if por_soporte and "Periodo Mes N" in df.columns:
        df["Año"] = pd.to_numeric(df["Periodo Año"], errors="coerce")
        df["Mes"] = pd.to_numeric(df["Periodo Mes N"], errors="coerce").map(NOMBRE_MES)
    else:
        c_fecha = col(df, "fecha", "recep")
        f = pd.to_datetime(df[c_fecha], errors="coerce", format="mixed") if c_fecha else pd.NaT
        df["Año"] = f.dt.year
        df["Mes"] = f.dt.month.map(NOMBRE_MES)
    df = df.drop(columns=["Periodo Mes N"], errors="ignore")
    c_valor = col(df, "valor")
    df["Valor (número)"] = df[c_valor].map(a_numero) if c_valor else 0.0
    return df


COLS_HIST = {
    "clave": "TEXT PRIMARY KEY", "contrato": "TEXT", "recepcion": "TEXT", "ips": "TEXT",
    "fecha_recepcion": "TEXT", "estado": "TEXT", "radicacion": "TEXT", "valor": "REAL",
    "primera_vez": "TEXT", "ultima_vez": "TEXT", "periodo_anio": "INTEGER",
    "periodo_mes": "INTEGER", "fecha_min": "TEXT", "fecha_max": "TEXT", "fuente": "TEXT",
    "regimen": "TEXT",
}


def abrir_db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS registros(" +
                ", ".join(f"{k} {v}" for k, v in COLS_HIST.items()) + ")")
    existentes = {r[1] for r in con.execute("PRAGMA table_info(registros)")}
    for k, v in COLS_HIST.items():
        if k not in existentes:
            con.execute(f"ALTER TABLE registros ADD COLUMN {k} {v.replace('PRIMARY KEY', '')}")
    # qué contrato + mes se consultó y cuándo (para distinguir "pendiente" de "no consultado")
    cols = {r[1] for r in con.execute("PRAGMA table_info(consultas)")}
    if cols and "regimen" not in cols:  # versión anterior sin régimen → se migra como RS
        con.execute("ALTER TABLE consultas RENAME TO consultas_v1")
    con.execute("""CREATE TABLE IF NOT EXISTS consultas(
        contrato TEXT, anio INTEGER, mes INTEGER, regimen TEXT, fecha TEXT, resultado TEXT,
        PRIMARY KEY (contrato, anio, mes, regimen))""")
    if cols and "regimen" not in cols:
        con.execute("INSERT OR IGNORE INTO consultas SELECT contrato, anio, mes, 'RS', fecha, resultado "
                    "FROM consultas_v1")
        con.execute("DROP TABLE consultas_v1")
    con.execute("""CREATE TABLE IF NOT EXISTS corridas(
        fecha TEXT PRIMARY KEY, meses TEXT, contratos INTEGER, radicados INTEGER,
        pendientes INTEGER, errores INTEGER, novedades INTEGER)""")
    return con


def actualizar_historial(df, regimen):
    """Guarda TODO lo encontrado (cualquier mes) y devuelve lo que es nuevo o cambió."""
    con = abrir_db()
    ahora = datetime.now().isoformat(timespec="seconds")
    c_rec = col(df, "recepci", "rips") or col(df, "recepci")
    c_ips, c_est = col(df, "ips"), col(df, "estado")
    c_rad = col(df, "radicaci")
    c_fec = col(df, "fecha", "recep")
    hay_previos = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0] > 0
    nuevos = []
    for i, r in df.iterrows():
        g = lambda c: (None if c is None or pd.isna(r.get(c)) else r.get(c))
        clave = f"{r['Contrato Consultado']}|{g(c_rec) or ''}"
        previo = con.execute("SELECT estado, radicacion FROM registros WHERE clave=?",
                             (clave,)).fetchone()
        est, rad = g(c_est) or "", g(c_rad) or ""
        anio = int(r["Año"]) if pd.notna(r.get("Año")) else None
        mes = MESES.get(str(r.get("Mes") or "").lower())
        datos = dict(contrato=r["Contrato Consultado"], recepcion=g(c_rec) or "",
                     ips=g(c_ips) or "", fecha_recepcion=g(c_fec) or "", estado=est,
                     radicacion=rad, valor=float(r.get("Valor (número)") or 0),
                     periodo_anio=anio, periodo_mes=mes,
                     fecha_min=g("Fecha atención mín") or "", fecha_max=g("Fecha atención máx") or "",
                     fuente=g("Fuente periodo") or "", regimen=r.get("Régimen") or regimen,
                     ultima_vez=ahora)
        if previo is None:
            nuevos.append(i)
            datos.update(clave=clave, primera_vez=ahora)
            con.execute(f"INSERT INTO registros ({','.join(datos)}) VALUES "
                        f"({','.join('?' * len(datos))})", list(datos.values()))
        else:
            if (previo[0], previo[1]) != (est, rad):
                nuevos.append(i)
            con.execute(f"UPDATE registros SET {', '.join(k + '=?' for k in datos)} WHERE clave=?",
                        list(datos.values()) + [clave])
    con.commit()
    con.close()
    return df.loc[nuevos], not hay_previos


def registrar_consultas(resumen, meses, anio, regimen, contratos=None, df=None):
    # meses radicados por contrato y régimen (según el periodo de cada soporte)
    res_reg = {}
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            m = MESES.get(str(r.get("Mes") or "").lower())
            if m:
                res_reg.setdefault(r["Contrato Consultado"], {}).setdefault(r.get("Régimen") or regimen, set()).add(m)
    con = abrir_db()
    ahora = datetime.now().isoformat(timespec="seconds")
    for _, f in resumen.iterrows():
        if contratos is not None and f["Contrato"] not in contratos:
            continue
        for m in meses:
            # los contratos con error en este régimen ya vienen excluidos (se registran aparte)
            res = "RADICADO" if m in res_reg.get(f["Contrato"], {}).get(regimen, set()) else "SIN RADICAR"
            con.execute("INSERT OR REPLACE INTO consultas VALUES (?,?,?,?,?,?)",
                        (f["Contrato"], anio, m, regimen, ahora, res))
    con.commit()
    con.close()


def guardar_excel(df, contratos, meta, meses, anio, novedades, errores, fuera, sin_periodo=None):
    DESCARGAS.mkdir(exist_ok=True)
    etiqueta = "-".join(NOMBRE_MES[m] for m in meses) if meses else "todos"
    ruta = DESCARGAS / f"Radicacion_Capita_{etiqueta}_{anio}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    visibles = [c for c in df.columns if not c.startswith("_")] if not df.empty else []

    # Matriz contrato x mes: cuántas radicaciones y por qué valor
    filas = []
    for c in contratos:
        sub = df[df["Contrato Consultado"] == c] if not df.empty else df
        m_ = meta.get(c, {})
        fila = {"Contrato": c, "Prestador": m_.get("prestador", ""),
                "Municipio": m_.get("municipio", ""), "Inicio": m_.get("inicio", "")}
        for m in (meses or []):
            sm = sub[sub["Mes"] == NOMBRE_MES[m]] if not sub.empty else sub
            fila[f"{NOMBRE_MES[m]} - Radicados"] = len(sm)
            fila[f"{NOMBRE_MES[m]} - Valor"] = float(sm["Valor (número)"].sum()) if len(sm) else 0.0
        fila["Total radicados"] = len(sub)
        err = next((v for k, v in errores.items() if k == c or k.startswith(c + " (")), None)
        fila["Estado"] = ("ERROR: " + err) if err else \
            "FUERA DE VIGENCIA" if c in fuera else ("RADICADO" if len(sub) else "SIN RADICAR")
        filas.append(fila)
    resumen = pd.DataFrame(filas)

    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        (df[visibles] if visibles else pd.DataFrame()).to_excel(xw, sheet_name="Detalle", index=False)
        (novedades[[c for c in novedades.columns if not c.startswith("_")]] if len(novedades)
         else pd.DataFrame({"Info": ["Sin novedades"]})).to_excel(xw, sheet_name="Novedades", index=False)
        resumen[resumen["Estado"] == "SIN RADICAR"].to_excel(xw, sheet_name="Pendientes", index=False)
        if sin_periodo is not None and len(sin_periodo):
            sin_periodo[[c for c in sin_periodo.columns if not c.startswith("_")]].to_excel(
                xw, sheet_name="Revisar (sin periodo)", index=False)
        for ws in xw.book.worksheets:
            for colcells in ws.columns:
                ancho = max(len(str(c.value or "")) for c in colcells[:200])
                ws.column_dimensions[colcells[0].column_letter].width = min(max(ancho + 2, 10), 45)
            ws.freeze_panes = "A2"
    return ruta, resumen


# ------------------------------------------------------------------ dashboard
def armar_dashboard(meta, ultima):
    """JSON para el dashboard: todo el historial + el listado de contratos.
    No incluye datos de pacientes (los soportes RIPS se quedan en este equipo)."""
    con = abrir_db()
    con.row_factory = sqlite3.Row
    regs = [dict(r) for r in con.execute(
        "SELECT contrato, recepcion, ips, fecha_recepcion, estado, radicacion, valor, "
        "periodo_anio, periodo_mes, fecha_min, fecha_max, fuente, regimen, primera_vez "
        "FROM registros ORDER BY contrato, periodo_anio, periodo_mes")]
    cons = [dict(r) for r in con.execute("SELECT * FROM consultas")]
    corr = [dict(r) for r in con.execute("SELECT * FROM corridas ORDER BY fecha DESC LIMIT 30")]
    con.close()
    contratos = [{"contrato": k, **v} for k, v in meta.items()]
    return {"generado": datetime.now().isoformat(timespec="seconds"), "version": 1,
            "contratos": contratos, "registros": regs, "consultas": cons,
            "corridas": corr, "ultima": ultima}


def publicar(datos):
    """Sube el JSON al dashboard de Vercel (POST /api/subir con token)."""
    url = (os.getenv("SIE_DASHBOARD_URL") or "").rstrip("/")
    token = os.getenv("SIE_DASHBOARD_TOKEN") or ""
    local = DESCARGAS / "dashboard.json"
    DESCARGAS.mkdir(exist_ok=True)
    local.write_text(json.dumps(datos, ensure_ascii=False, default=str), encoding="utf-8")
    if not url or not token:
        log("Dashboard: sin SIE_DASHBOARD_URL/SIE_DASHBOARD_TOKEN en .env → solo copia local")
        return False
    req = urllib.request.Request(
        f"{url}/api/subir", method="POST",
        data=json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            log(f"Dashboard actualizado ✔ ({r.status}) {url}")
            return True
    except urllib.error.HTTPError as e:
        log(f"Dashboard: error {e.code} {e.read()[:200]!r}")
    except Exception as e:
        log(f"Dashboard: no se pudo publicar ({e})")
    return False


# ---------------------------------------------------------------------- main
def main():
    load_dotenv(BASE / ".env")
    ap = argparse.ArgumentParser(description="Seguimiento de radicación Cápita en SIE Dusakawi")
    ap.add_argument("meses", nargs="*", help="enero febrero … (o números 1-12)")
    ap.add_argument("--todos", action="store_true", help="no filtrar por mes")
    ap.add_argument("--anio", type=int, default=int(os.getenv("SIE_ANIO", datetime.now().year)))
    ap.add_argument("--regimen", default=os.getenv("SIE_REGIMEN", "RS,RC"),
                    help="Regímenes separados por coma: RS,RC (por defecto ambos)")
    ap.add_argument("--tipo", default=os.getenv("SIE_TIPO_CONTRATO", "Capita"))
    ap.add_argument("--estado", default="Radicado")
    ap.add_argument("--contratos", default=os.getenv("SIE_CONTRATOS", str(BASE / "contratos.xlsx")))
    ap.add_argument("--solo", nargs="*", help="consultar solo estos contratos (prueba)")
    ap.add_argument("--cantidad", type=int, default=5000)
    ap.add_argument("--oculto", action="store_true", help="navegador sin ventana")
    ap.add_argument("--sin-soportes", action="store_true",
                    help="no descargar soportes RIPS (más rápido; usa Fecha Recepción)")
    ap.add_argument("--por-recepcion", action="store_true",
                    help="filtrar meses por Fecha Recepción en vez del periodo del soporte")
    ap.add_argument("--incluir-fuera-vigencia", action="store_true",
                    help="consultar también contratos que no estaban vigentes en esos meses")
    ap.add_argument("--no-publicar", action="store_true", help="no subir al dashboard")
    a = ap.parse_args()

    if not a.meses and not a.todos:
        ap.error("Indica meses (ej: enero febrero) o usa --todos")
    meses = [] if a.todos else parsear_meses(a.meses)
    contratos, meta = cargar_contratos(a.contratos)
    if a.solo:
        contratos = [c for c in contratos if c in a.solo] or a.solo
    if not contratos:
        sys.exit("El listado de contratos está vacío.")
    regimenes = [r.strip().upper() for r in (a.regimen or "").split(",") if r.strip()] or [""]
    fuera = set() if a.incluir_fuera_vigencia else \
        {c for c in contratos if not vigente_en(meta.get(c, {}), a.anio, meses)}
    a_consultar = [c for c in contratos if c not in fuera]

    usuario = os.getenv("SIE_USUARIO") or input("Usuario SIE: ").strip()
    clave = os.getenv("SIE_CLAVE")
    if not clave:
        if not sys.stdin.isatty():
            sys.exit("ERROR: falta SIE_CLAVE en bot/.env (modo servidor)")
        clave = getpass.getpass("Clave SIE: ")

    log(f"{len(contratos)} contratos ({len(fuera)} fuera de vigencia, se consultan "
        f"{len(a_consultar)}) | meses: {', '.join(NOMBRE_MES[m] for m in meses) or 'todos'} "
        f"{a.anio} | régimen {', '.join(regimenes)} · {a.tipo} · {a.estado}")

    partes, errores = [], {}
    sin_periodo = pd.DataFrame()
    if a_consultar:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=a.oculto, slow_mo=0 if a.oculto else 80)
            page = browser.new_page(viewport={"width": 1500, "height": 950},
                                    accept_downloads=True)
            page.set_default_timeout(30000)
            try:
                iniciar_sesion(page, usuario, clave, a.anio)
                abrir_consulta(page)
                total = len(a_consultar) * len(regimenes)
                n = 0
                for reg in regimenes:
                    tipo = f"{a.tipo} {reg}" if reg else a.tipo   # "Capita RS" / "Capita RC"
                    log(f"=== Régimen {reg or '(sin filtro)'} · {tipo} ===")
                    for contrato in a_consultar:
                        n += 1
                        clave_err = f"{contrato} ({reg})" if len(regimenes) > 1 else contrato
                        for intento in (1, 2):
                            try:
                                configurar_filtros(page, reg, tipo, a.estado, a.cantidad)
                                df = buscar_contrato(page, contrato, not a.sin_soportes, reg)
                                log(f"[{n}/{total}] {contrato} {reg}: {len(df)} registros")
                                if not df.empty:
                                    partes.append(df)
                                errores.pop(clave_err, None)
                                break
                            except Exception as e:
                                errores[clave_err] = str(e).splitlines()[0][:150]
                                log(f"[{n}/{total}] {contrato} {reg}: error ({errores[clave_err]})")
                                evidencia(page, f"error_{re.sub(r'[^A-Za-z0-9-]', '_', contrato)}_{reg}")
                                if intento == 1:
                                    abrir_consulta(page)  # recargar la página y reintentar
            finally:
                browser.close()

    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["Contrato Consultado", "Mes", "Año", "Valor (número)"])
    novedades, primera = df.iloc[0:0], True
    if not df.empty:
        df = preparar(df, not (a.por_recepcion or a.sin_soportes))
        sin_periodo = df[df["Mes"].isna()]
        novedades, primera = actualizar_historial(df, regimenes[0])  # todo lo hallado, todos los meses
        if meses:
            sel = (df["Año"] == a.anio) & (df["Mes"].isin([NOMBRE_MES[m] for m in meses]))
            df = df[sel]
            novedades = novedades[novedades.index.isin(df.index)]

    ruta, resumen = guardar_excel(df, contratos, meta, meses, a.anio, novedades, errores,
                                  fuera, sin_periodo)
    if meses:
        for reg in regimenes:
            con_error = {k.split(" (")[0] for k in errores if k.endswith(f"({reg})") or "(" not in k}
            registrar_consultas(resumen, meses, a.anio, reg,
                                contratos=set(a_consultar) - con_error, df=df)
            if con_error:  # los que fallaron en este régimen quedan como ERROR
                c = abrir_db()
                for ce in con_error:
                    for m in meses:
                        c.execute("INSERT OR REPLACE INTO consultas VALUES (?,?,?,?,?,?)",
                                  (ce, a.anio, m, reg, datetime.now().isoformat(timespec="seconds"),
                                   "ERROR: " + next((v for k, v in errores.items() if k.startswith(ce)), "")))
                c.commit()
                c.close()

    radicados = int((resumen["Estado"] == "RADICADO").sum())
    pendientes = int((resumen["Estado"] == "SIN RADICAR").sum())
    con = abrir_db()
    con.execute("INSERT OR REPLACE INTO corridas VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"),
                 ",".join(str(m) for m in meses) or "todos", len(contratos), radicados,
                 pendientes, len(errores), 0 if primera else len(novedades)))
    con.commit()
    con.close()

    print("\n" + "=" * 60)
    print(f" Contratos con radicación : {radicados}/{len(contratos)}")
    print(f" Contratos sin radicar    : {pendientes}")
    print(f" Fuera de vigencia        : {len(fuera)}")
    print(f" Contratos con error      : {len(errores)}")
    print(f" Registros del periodo    : {len(df)}")
    if len(sin_periodo):
        print(f" Soportes sin fecha/error : {len(sin_periodo)} (hoja 'Revisar')")
    if not primera:
        print(f" NOVEDADES desde la última vez: {len(novedades)}")
    print(f" Excel: {ruta}")
    print(f"@@EXCEL {ruta}", flush=True)
    print("=" * 60)

    if not a.no_publicar:
        publicar(armar_dashboard(meta, {
            "fecha": datetime.now().isoformat(timespec="seconds"), "anio": a.anio,
            "meses": meses, "radicados": radicados, "pendientes": pendientes,
            "fuera_vigencia": len(fuera), "errores": errores,
            "novedades": [] if primera else
            [f"{r['Contrato Consultado']}|{r.get(col(df, 'recepci', 'rips') or '', '')}"
             for _, r in novedades.iterrows()]}))

    aviso = f"{radicados}/{len(contratos)} contratos radicados, {pendientes} pendientes"
    if len(novedades) and not primera:
        aviso = f"{len(novedades)} radicaciones nuevas. " + aviso
    notificar("SIE · Radicación Cápita", aviso)
    if sys.platform == "darwin" and sys.stdout.isatty():
        subprocess.run(["open", str(ruta)], check=False)


if __name__ == "__main__":
    main()
