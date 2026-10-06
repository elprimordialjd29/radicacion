"""
Worker de radicación — corre en el servidor (VPS) junto al bot.

Recibe consultas desde el dashboard (vía /api/consultas de Vercel, con token),
las pone en cola y las ejecuta UNA a la vez con bot/sie_bot.py (Playwright).
Al terminar, el bot publica los resultados en el dashboard.

Endpoints (todos exigen el header x-token = WORKER_TOKEN):
  GET  /salud
  GET  /consultas                 últimas consultas (estado, progreso)
  POST /consultas                 nueva consulta
  GET  /consultas/{id}            detalle + log
  GET  /consultas/{id}/excel      descarga el Excel generado
  POST /consultas/{id}/cancelar   cancela (en cola o corriendo)
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parent.parent
BOT = RAIZ / "bot"
DATOS = BOT / "worker_datos"
DATOS.mkdir(exist_ok=True)
DB = DATOS / "consultas.db"
CATALOGO = DATOS / "contratos.json"

load_dotenv(BOT / ".env")
TOKEN = os.getenv("WORKER_TOKEN", "")
sys.path.insert(0, str(BOT))
import rips_json  # noqa: E402  (convertidor plano → JSON Res. 2275)
PY = str(BOT / ".venv" / "bin" / "python")

app = FastAPI(title="Radicación worker", docs_url=None, redoc_url=None)
_lock = threading.Lock()
_hay_trabajo = threading.Event()
_proceso = {"id": None, "popen": None}


# ------------------------------------------------------------------ base de datos
def db():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS consultas(
        id TEXT PRIMARY KEY, creada TEXT, usuario TEXT, anio INTEGER, meses TEXT,
        contratos TEXT, sin_soportes INTEGER, estado TEXT, total INTEGER, hechos INTEGER,
        actual TEXT, inicio TEXT, fin TEXT, excel TEXT, resumen TEXT, log TEXT)""")
    if "regimenes" not in {r[1] for r in con.execute("PRAGMA table_info(consultas)")}:
        con.execute("ALTER TABLE consultas ADD COLUMN regimenes TEXT DEFAULT 'RS'")
    return con


def fila(r, con_log=False):
    d = dict(r)
    d["meses"] = json.loads(d["meses"] or "[]")
    d["contratos"] = json.loads(d["contratos"] or "[]")
    d["n_contratos"] = len(d["contratos"])
    if len(d["contratos"]) > 20:
        d["contratos"] = d["contratos"][:20] + ["…"]
    d["tiene_excel"] = bool(d.pop("excel"))
    log = d.pop("log") or ""
    if con_log:
        d["log"] = log[-15000:]
    return d


def actualizar(cid, **campos):
    with _lock, db() as con:
        con.execute(f"UPDATE consultas SET {', '.join(k + '=?' for k in campos)} WHERE id=?",
                    [*campos.values(), cid])


def auth(tok):
    if not TOKEN or tok != TOKEN:
        raise HTTPException(401, "Token inválido")


# ------------------------------------------------------------------ ejecución
RE_PROG = re.compile(r"\[(\d+)/(\d+)\]\s+(\S+)")
RE_TOTAL = re.compile(r"se consultan (\d+)\)")


def ejecutar(r):
    cid = r["id"]
    args = [PY, "-u", str(BOT / "sie_bot.py")]
    meses = json.loads(r["meses"])
    args += [str(m) for m in meses] if meses else ["--todos"]
    args += ["--anio", str(r["anio"]), "--oculto", "--contratos", str(CATALOGO)]
    contratos = json.loads(r["contratos"])
    if contratos:
        args += ["--solo", *contratos]
    if r["sin_soportes"]:
        args.append("--sin-soportes")
    args += ["--regimen", r["regimenes"] or "RS,RC"]

    actualizar(cid, estado="corriendo", inicio=datetime.now().isoformat(timespec="seconds"))
    log, excel = [], None
    p = subprocess.Popen(args, cwd=BOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    _proceso.update(id=cid, popen=p)
    for linea in p.stdout:
        linea = linea.rstrip()
        log.append(linea)
        campos = {"log": "\n".join(log[-400:])}
        if (m := RE_TOTAL.search(linea)):
            campos["total"] = int(m.group(1))
        if (m := RE_PROG.search(linea)):
            campos.update(hechos=int(m.group(1)), total=int(m.group(2)), actual=m.group(3).rstrip(":"))
        if linea.startswith("@@EXCEL "):
            excel = linea[8:].strip()
        actualizar(cid, **campos)
    code = p.wait()
    _proceso.update(id=None, popen=None)
    resumen = "\n".join(l for l in log if l.startswith(" ") and ":" in l)[-2000:]
    cancelada = db().execute("SELECT estado FROM consultas WHERE id=?", (cid,)).fetchone()["estado"] == "cancelando"
    actualizar(cid, estado="cancelada" if cancelada else ("terminada" if code == 0 else "error"),
               fin=datetime.now().isoformat(timespec="seconds"), excel=excel, resumen=resumen,
               log="\n".join(log[-400:]))


def bucle():
    # al arrancar, lo que quedó "corriendo" de un reinicio se marca como error
    with db() as con:
        con.execute("UPDATE consultas SET estado='error', fin=? WHERE estado IN ('corriendo','cancelando')",
                    (datetime.now().isoformat(timespec="seconds"),))
    while True:
        r = db().execute("SELECT * FROM consultas WHERE estado='en_cola' ORDER BY creada LIMIT 1").fetchone()
        if not r:
            _hay_trabajo.wait(30)
            _hay_trabajo.clear()
            continue
        try:
            ejecutar(r)
        except Exception as e:  # nunca matar el bucle
            actualizar(r["id"], estado="error", fin=datetime.now().isoformat(timespec="seconds"),
                       resumen=f"Error interno: {e}")


threading.Thread(target=bucle, daemon=True).start()


# ------------------------------------------------------------------ API
class Contrato(BaseModel):
    contrato: str
    prestador: Optional[str] = ""
    nit: Optional[str] = ""
    municipio: Optional[str] = ""
    inicio: Optional[str] = ""
    fin: Optional[str] = ""
    estado_contrato: Optional[str] = ""
    valor_contrato: Optional[str] = ""


class NuevaConsulta(BaseModel):
    anio: int = Field(ge=2020, le=2100)
    meses: List[int] = []
    contratos: List[str] = []          # vacío = todos los del catálogo
    catalogo: List[Contrato] = []      # listado completo (lo manda el dashboard)
    usuario: str = "desconocido"
    sin_soportes: bool = False
    regimenes: List[str] = ["RS", "RC"]


@app.get("/salud")
def salud(x_token: str = Header("")):
    auth(x_token)
    pendientes = db().execute("SELECT COUNT(*) FROM consultas WHERE estado='en_cola'").fetchone()[0]
    return {"ok": True, "corriendo": _proceso["id"], "en_cola": pendientes,
            "catalogo": CATALOGO.exists()}


@app.get("/consultas")
def listar(limit: int = 20, x_token: str = Header("")):
    auth(x_token)
    rs = db().execute("SELECT * FROM consultas ORDER BY creada DESC LIMIT ?", (min(limit, 100),)).fetchall()
    return [fila(r) for r in rs]


@app.post("/consultas")
def crear(c: NuevaConsulta, x_token: str = Header("")):
    auth(x_token)
    if any(m < 1 or m > 12 for m in c.meses):
        raise HTTPException(400, "Mes inválido")
    regs = sorted({r.upper() for r in c.regimenes if r.upper() in ("RS", "RC")})
    if not regs:
        raise HTTPException(400, "Elige al menos un régimen (RS o RC)")
    if c.catalogo:
        CATALOGO.write_text(json.dumps([x.model_dump() for x in c.catalogo], ensure_ascii=False),
                            encoding="utf-8")
    if not CATALOGO.exists():
        raise HTTPException(400, "No hay listado de contratos en el servidor")
    validos = {x["contrato"] for x in json.loads(CATALOGO.read_text(encoding="utf-8"))}
    desconocidos = [x for x in c.contratos if x not in validos]
    if desconocidos:
        raise HTTPException(400, f"Contratos que no están en el listado: {desconocidos[:5]}")
    activa = db().execute("SELECT id FROM consultas WHERE estado IN ('en_cola','corriendo') AND anio=? "
                          "AND meses=? AND contratos=? AND regimenes=?",
                          (c.anio, json.dumps(sorted(c.meses)), json.dumps(sorted(c.contratos)),
                           ",".join(regs))).fetchone()
    if activa:
        return {"id": activa["id"], "duplicada": True}
    cid = uuid.uuid4().hex[:10]
    with _lock, db() as con:
        con.execute("INSERT INTO consultas (id, creada, usuario, anio, meses, contratos, sin_soportes, "
                    "estado, total, hechos, regimenes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, datetime.now().isoformat(timespec="seconds"), c.usuario[:60], c.anio,
                     json.dumps(sorted(c.meses)), json.dumps(sorted(c.contratos)), int(c.sin_soportes),
                     "en_cola", (len(c.contratos) or len(validos)) * len(regs), 0, ",".join(regs)))
    _hay_trabajo.set()
    return {"id": cid}


@app.get("/consultas/{cid}")
def detalle(cid: str, x_token: str = Header("")):
    auth(x_token)
    r = db().execute("SELECT * FROM consultas WHERE id=?", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "No existe")
    return fila(r, con_log=True)


@app.get("/consultas/{cid}/excel")
def excel(cid: str, x_token: str = Header("")):
    auth(x_token)
    r = db().execute("SELECT excel FROM consultas WHERE id=?", (cid,)).fetchone()
    if not r or not r["excel"]:
        raise HTTPException(404, "Sin Excel")
    ruta = (BOT / r["excel"]).resolve() if not os.path.isabs(r["excel"]) else Path(r["excel"]).resolve()
    if BOT.resolve() not in ruta.parents or not ruta.exists():
        raise HTTPException(404, "Sin Excel")
    return FileResponse(ruta, filename=ruta.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/consultas/{cid}/cancelar")
def cancelar(cid: str, x_token: str = Header("")):
    auth(x_token)
    r = db().execute("SELECT estado FROM consultas WHERE id=?", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "No existe")
    if r["estado"] == "en_cola":
        actualizar(cid, estado="cancelada", fin=datetime.now().isoformat(timespec="seconds"))
    elif r["estado"] == "corriendo" and _proceso["id"] == cid:
        actualizar(cid, estado="cancelando")
        _proceso["popen"].terminate()
    return {"ok": True}


# ------------------------------------------------------------------ RIPS
def _limpio(x):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(x)).strip("_") or "sin_nombre"


@app.get("/rips")
def rips(contrato: str, anio: int, mes: int, regimen: str = "", formato: str = "txt",
         x_token: str = Header("")):
    """Soporte(s) RIPS de un contrato para un periodo de atención (y régimen).
    Un archivo → se entrega directo; varios → .zip. formato = txt (original SIE) | json (Res. 2275)."""
    auth(x_token)
    formato = formato.lower()
    if formato not in ("txt", "json"):
        raise HTTPException(400, "formato debe ser txt o json")
    hist = BOT / "historial.db"
    if not hist.exists():
        raise HTTPException(404, "Sin historial")
    con = sqlite3.connect(hist)
    sql = "SELECT recepcion, regimen FROM registros WHERE contrato=? AND periodo_anio=? AND periodo_mes=?"
    params = [contrato, anio, mes]
    if regimen:
        sql += " AND regimen=?"
        params.append(regimen.upper())
    filas = con.execute(sql + " ORDER BY recepcion", params).fetchall()
    con.close()
    carpeta = BOT / "descargas" / "soportes" / _limpio(contrato)
    archivos = []
    for recepcion, reg in filas:
        encontrados = sorted(carpeta.glob(f"{_limpio(recepcion)}__*"))
        if encontrados:
            archivos.append((recepcion, reg or "", encontrados[0]))
    if not archivos:
        raise HTTPException(404, "No hay soportes descargados para ese periodo")

    base = f"RIPS_{_limpio(contrato)}_{anio}-{mes:02d}"
    def nombre(rec, reg):
        return f"{base}_{reg or 'NA'}_rec{_limpio(rec)}.{formato}"

    def contenido(ruta):
        if formato == "json":
            return rips_json.convertir(ruta).encode("utf-8")
        return ruta.read_bytes()

    tipo = "application/json" if formato == "json" else "text/plain; charset=latin-1"
    if len(archivos) == 1:
        rec, reg, ruta = archivos[0]
        return Response(contenido(ruta), media_type=tipo,
                        headers={"Content-Disposition": f'attachment; filename="{nombre(rec, reg)}"'})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rec, reg, ruta in archivos:
            z.writestr(nombre(rec, reg), contenido(ruta))
    sufijo = f"_{regimen.upper()}" if regimen else ""
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{base}{sufijo}_{formato}.zip"'})
