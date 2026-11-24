"""Frecuencia de uso: cuántas veces se reportó cada CUPS (y cada diagnóstico) en los RIPS.

- El catálogo se carga por TIPO de contrato (DNT, PMS, ASE…): actividades con sus CUPS y
  diagnósticos (CIE-10) con su grupo. Se pega desde Excel (dos columnas).
- Cada soporte RIPS se lee UNA vez y se guarda un resumen en caché (todos los códigos, no solo los
  del catálogo), así que cambiar el catálogo no obliga a releer los archivos.
- "Pacientes con diagnóstico" = pacientes que en ese RIPS tienen algún servicio con un diagnóstico
  del catálogo (principal o relacionado). Así también cuentan OTROS SERVICIOS, que no traen diagnóstico.
"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path

DEPARTAMENTOS = {"05": "ANTIOQUIA", "08": "ATLÁNTICO", "11": "BOGOTÁ", "13": "BOLÍVAR", "20": "CESAR",
                 "23": "CÓRDOBA", "44": "LA GUAJIRA", "47": "MAGDALENA", "54": "NORTE DE SANTANDER",
                 "70": "SUCRE"}

# campo del código de la tecnología y campos de diagnóstico de cada sección (nombres de rips_json)
CAMPOS = {
    "CONSULTAS": ("codConsulta", ["codDiagnosticoPrincipal", "codDiagnosticoRelacionado1",
                                  "codDiagnosticoRelacionado2", "codDiagnosticoRelacionado3"]),
    "PROCEDIMIENTOS": ("codProcedimiento", ["codDiagnosticoPrincipal", "codDiagnosticoRelacionado"]),
    "MEDICAMENTOS": ("codTecnologiaSalud", ["codDiagnosticoPrincipal", "codDiagnosticoRelacionado"]),
    "OTROS": ("codTecnologiaSalud", []),
    "URGENCIAS": (None, ["codDiagnosticoPrincipal", "codDiagnosticoPrincipalE", "codDiagnosticoRelacionadoE1",
                         "codDiagnosticoRelacionadoE2", "codDiagnosticoRelacionadoE3"]),
    "HOSPITALIZACION": (None, ["codDiagnosticoPrincipal", "codDiagnosticoPrincipalE", "codDiagnosticoRelacionadoE1",
                               "codDiagnosticoRelacionadoE2", "codDiagnosticoRelacionadoE3"]),
}
RE_CIE = re.compile(r"^[A-Z]\d{2}[0-9X]?$")
VERSION_CACHE = 1
# tipos de contrato que se cuentan con la matriz 3280 (versión sencilla); TODOS = toda la EPS;
# los demás, como la Evaluación Cápita Asistencial; un tipo con catálogo cargado usa su catálogo (p. ej. DNT)
TIPOS_3280 = {"PMS", "RCV"}
# registros de los archivos de urgencias y hospitalización del RIPS (no traen código de servicio)
NOMBRES_SECCION = {"URGENCIAS": "Atención de urgencias (archivo de urgencias del RIPS)",
                   "HOSPITALIZACION": "Hospitalización (archivo de hospitalización del RIPS)"}
ARCHIVO_RIPS = {"consultas": "Consultas", "procedimientos": "Procedimientos", "medicamentos": "Medicamentos",
                "otrosServicios": "Otros servicios"}


def _clave_cargue(f):
    """Orden de los cargues: f = (recepcion, regimen, fecha_recepcion, …). Manda el NÚMERO DE RECEPCIÓN RIPS, que el SIE
    asigna en orden al cargar (la «Fecha Recepción» puede quedar vieja: al volver a cargar el RIPS de una misma factura
    el SIE le deja la fecha de la radicación original); la fecha solo desempata."""
    return (int(re.sub(r"\D", "", str(f[0])) or 0), str(f[2] or ""))


def ultimos_por_regimen(filas):
    """Regla del usuario: si un prestador vuelve a cargar el RIPS del mismo mes y régimen y el SIE deja las dos
    radicaciones vigentes, se usa solo el ÚLTIMO cargue (número de recepción RIPS más alto). Una fila por régimen."""
    mejor = {}
    for f in filas:
        rg = f[1] or ""
        if rg not in mejor or _clave_cargue(f) > _clave_cargue(mejor[rg]):
            mejor[rg] = f
    return [mejor[k] for k in sorted(mejor)]


def tipo_contrato(contrato):
    """Tipo del contrato igual que en la pantalla (tipoDe): «MD-RCV-20001-…» → MD-RCV, «PMS-44001-…» → PMS."""
    m = re.match(r"^[A-Z]+(?:-[A-Z]+)?(?=-\d)", str(contrato or "").upper())
    return m.group(0) if m else ""


def departamento(contrato):
    m = re.match(r"^[A-Z]+(?:-[A-Z]+)*-(\d{2})\d{3}-", contrato or "")
    return DEPARTAMENTOS.get(m.group(1), f"Dpto {m.group(1)}") if m else "—"


def _codigo(c):
    return re.sub(r"\s+", "", str(c or "")).upper()


# ------------------------------------------------------------------ catálogo (pegado desde Excel)
def _filas(texto):
    """Filas de un pegado de Excel (tabulaciones; celdas con saltos de línea van entre comillas)."""
    texto = (texto or "").replace("\r\n", "\n").strip("\n")
    sep = "\t" if "\t" in texto else (";" if texto.count(";") > texto.count(",") else ",")
    return [[c.strip() for c in f] for f in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in f)]


def _grupo(t):
    return re.sub(r"\s+", " ", str(t or "")).strip().upper()


def parse_catalogo(texto_act, texto_dx):
    """Actividades: 3 columnas GRUPO · DESCRIPCIÓN · CUPS (el grupo puede venir solo en una fila de un
    bloque combinado de Excel: se rellena hacia abajo; las filas antes del primer grupo van al primero)
    o 2 columnas DESCRIPCIÓN · CUPS (un solo grupo). Diagnósticos: CIE-10 · GRUPO."""
    filas = [f for f in _filas(texto_act)
             if not (len(f) >= 2 and any(x.upper().startswith("DESCRIPCION") for x in f) and "CUPS" in " ".join(f).upper())]
    tres = any(len(f) >= 3 for f in filas)
    crudas, grupo, pendientes = [], "", []
    for f in filas:
        f = f + [""] * (3 - len(f))
        g, desc, cods = (f[0], f[1], f[2]) if tres else ("", f[0], f[1])
        if g.strip():
            grupo = _grupo(g)
            for r in pendientes:   # filas sin grupo antes del primero → ese grupo
                r[0] = grupo
            pendientes = []
        r = [grupo, desc.strip(), cods]
        crudas.append(r)
        if not grupo:
            pendientes.append(r)
    grupos, actividades, sin_codigo = [], {}, []
    for g, desc, cods in crudas:
        g = g or "GENERAL"
        if g not in grupos:
            grupos.append(g)
        codigos = [_codigo(x) for x in re.split(r"[,;\n]+|\s+(?=\d)", cods) if _codigo(x)]
        codigos = [c for c in codigos if c not in ("N/A", "NA", "-")]
        if not codigos:
            if desc and {"grupo": g, "descripcion": desc} not in sin_codigo:
                sin_codigo.append({"grupo": g, "descripcion": desc})
            continue
        for c in codigos:
            a = actividades.setdefault((g, c), {"grupo": g, "codigo": c, "descripciones": []})
            if desc and desc.upper() not in [d.upper() for d in a["descripciones"]]:
                a["descripciones"].append(desc)
    diagnosticos = {}
    for f in _filas(texto_dx):
        f = f + [""] * (2 - len(f))
        a, b = _codigo(f[0]), f[1].strip()
        cod, gr = (a, b) if RE_CIE.match(a) else (_codigo(b), f[0].strip())
        if RE_CIE.match(cod):
            gr = _grupo(gr) or (grupos[0] if len(grupos) == 1 else "GENERAL")
            diagnosticos.setdefault(cod, {"codigo": cod, "grupo": gr})
            if gr not in grupos:
                grupos.append(gr)
    return {"grupos": grupos, "actividades": list(actividades.values()), "sin_codigo": sin_codigo,
            "diagnosticos": list(diagnosticos.values())}


class Frecuencia:
    def __init__(self, datos_dir, bot_dir):
        self.dir = Path(datos_dir)
        self.bot = Path(bot_dir)
        self.ruta_cat = self.dir / "frecuencia_catalogo.json"
        self.cache = self.dir / "frecuencia_cache"
        self.cache.mkdir(exist_ok=True)
        sys.path.insert(0, str(self.bot))
        import rips_json   # noqa: E402
        self.rj = rips_json
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import motores   # noqa: E402
        self.M = motores
        # cola de cálculos en segundo plano (un proceso aparte por lote, para no cargar la memoria del worker)
        self._cola, self._en_curso = [], set()
        self._cola_lock, self._hay = threading.Lock(), threading.Event()
        threading.Thread(target=self._correr_cola, daemon=True).start()

    # ------------------------------------------------------------- catálogo
    def catalogo(self):
        return json.loads(self.ruta_cat.read_text(encoding="utf-8")) if self.ruta_cat.exists() else {}

    def guardar_catalogo(self, tipo, texto_act, texto_dx, usuario=""):
        cat = self.catalogo()
        nuevo = parse_catalogo(texto_act, texto_dx)
        if not nuevo["actividades"] and not nuevo["diagnosticos"]:
            raise ValueError("No se reconoció ningún CUPS ni diagnóstico en lo pegado")
        nuevo.update(actualizado=datetime.now().astimezone().isoformat(timespec="seconds"), por=usuario,
                     texto_actividades=texto_act, texto_diagnosticos=texto_dx)
        cat[tipo.upper()] = nuevo
        tmp = self.ruta_cat.with_suffix(".tmp")
        tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.ruta_cat)
        return nuevo

    # ------------------------------------------------------- lectura de RIPS
    def _resumen(self, ruta):
        """{svc: {codigo: {paciente: n}}, dxp: {paciente: [dx]}, dxs: {dx: n servicios}} de un soporte (en caché)."""
        st = ruta.stat()
        clave = hashlib.sha1(f"{VERSION_CACHE}|{ruta}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20]
        archivo = self.cache / f"{clave}.json"
        if archivo.exists():
            return json.loads(archivo.read_text(encoding="utf-8"))
        sec = self.rj.leer_plano(self.rj.leer_archivo(ruta))
        svc, dxp, dxs = {}, {}, {}
        for nombre, (campo_cod, campos_dx) in CAMPOS.items():
            lineas = sec.get(nombre, [])
            if not lineas:
                continue
            _, campos, campo_texto = self.rj.SERVICIOS[nombre]
            n = 3 + len(campos)
            nombres = ["_f", "_t", "_d"] + campos
            for l in lineas:
                p = self.rj._ajustar(self.rj._campos(l), n, campo_texto, nombres)
                reg = dict(zip(nombres, p))
                pac = f"{reg['_t']}{reg['_d']}"
                if campo_cod:
                    cod = _codigo(reg.get(campo_cod))
                    if cod:
                        d = svc.setdefault(cod, {})
                        d[pac] = d.get(pac, 0) + 1
                for cd in campos_dx:
                    dx = _codigo(reg.get(cd))
                    if dx and RE_CIE.match(dx):
                        dxp.setdefault(pac, set()).add(dx)
                        dxs[dx] = dxs.get(dx, 0) + 1
        out = {"svc": svc, "dxp": {k: sorted(v) for k, v in dxp.items()}, "dxs": dxs,
               "pacientes": len({l.split(",")[0] + l.split(",")[1] for l in sec.get("USUARIOS", []) if l.count(",") > 2})}
        archivo.write_text(json.dumps(out), encoding="utf-8")
        return out

    # -------------------------------------------------------------- cálculo
    def calcular(self, tipo, anio, meses, regimen, contratos_meta, hist):
        """Conteos por actividad/diagnóstico para TOTAL, departamento, municipio y contrato."""
        tipo = tipo.upper()
        cat = self.catalogo().get(tipo)
        if not cat:
            return {"tipo": tipo, "sin_catalogo": True}
        dxcat = {d["codigo"]: d["grupo"] for d in cat["diagnosticos"]}
        orden_g = cat.get("grupos") or sorted({d["grupo"] for d in cat["diagnosticos"]})
        sev = {gr: i for i, gr in enumerate(orden_g)}   # los grupos van de menos a más severo
        acts = [(a.get("grupo", "GENERAL"), a["codigo"]) for a in cat["actividades"]]
        cods = {c for _, c in acts}
        contratos = {c["contrato"]: c for c in contratos_meta if c["contrato"].upper().startswith(tipo + "-")}
        # grupos: clave → acumuladores (pacientes como conjuntos para no contar dos veces)
        grupos = {}

        def g(nivel, nombre):
            k = (nivel, nombre)
            if k not in grupos:
                grupos[k] = {"nivel": nivel, "nombre": nombre, "svc": {}, "pac": {}, "svc_dx": {}, "pac_dx": {},
                             "dx_pac": {}, "dx_svc": {}, "pacientes": set(), "pacientes_dx": set(), "archivos": 0,
                             "pac_grupo": {}}
            return grupos[k]

        carpeta = self.bot / "descargas" / "soportes"
        limpio = lambda x: re.sub(r"[^A-Za-z0-9._-]", "_", str(x)).strip("_") or "sin_nombre"
        meses_con = set()
        with closing(sqlite3.connect(hist)) as con:
            for contrato, meta in contratos.items():
                for m in meses:   # mes de atención m → cápita m+1
                    a_cap, m_cap = (anio + 1, 1) if m == 12 else (anio, m + 1)
                    sql = ("SELECT recepcion, regimen, fecha_recepcion FROM registros WHERE contrato=? AND periodo_anio=? "
                           "AND periodo_mes=? AND (fuente LIKE 'CONSULTAS%' OR fuente LIKE 'OTROS%') "
                           "AND estado NOT LIKE 'NO VIGENTE%'")
                    params = [contrato, a_cap, m_cap]
                    if regimen:
                        sql += " AND regimen=?"
                        params.append(regimen)
                    for rec, reg, _ in ultimos_por_regimen(con.execute(sql, params).fetchall()):   # último cargue
                        enc = sorted((carpeta / limpio(contrato)).glob(f"{limpio(rec)}__*"))
                        if not enc:
                            continue
                        meses_con.add(m)
                        R = self._resumen(enc[0])
                        pref = f"{contrato}|"   # un paciente es distinto en cada contrato
                        # cada paciente queda en el grupo MÁS SEVERO de sus diagnósticos del catálogo en ese RIPS
                        grupo_de = {}
                        for p, dxs in R["dxp"].items():
                            gs = [dxcat[d] for d in dxs if d in dxcat]
                            if gs:
                                grupo_de[p] = max(gs, key=lambda x: sev.get(x, -1))
                        destinos = [g("total", f"Total {tipo}"), g("departamento", departamento(contrato)),
                                    g("municipio", meta.get("municipio") or "—"),
                                    g("contrato", contrato)]
                        for G in destinos:
                            G["archivos"] += 1
                            for p, gr in grupo_de.items():
                                G["pac_grupo"].setdefault(gr, set()).add(pref + p)
                            for gr, cod in acts:
                                k = f"{gr}|{cod}"
                                for p, n in R["svc"].get(cod, {}).items():
                                    G["svc"][k] = G["svc"].get(k, 0) + n            # todos los pacientes
                                    G["pac"].setdefault(k, set()).add(pref + p)
                                    if grupo_de.get(p) == gr:                      # pacientes de ese grupo
                                        G["svc_dx"][k] = G["svc_dx"].get(k, 0) + n
                                        G["pac_dx"].setdefault(k, set()).add(pref + p)
                            for p, dxs in R["dxp"].items():
                                G["pacientes"].add(pref + p)
                                for d in dxs:
                                    if d in dxcat:
                                        G["dx_pac"].setdefault(d, set()).add(pref + p)
                                        G["pacientes_dx"].add(pref + p)
                            for d, n in R["dxs"].items():
                                if d in dxcat:
                                    G["dx_svc"][d] = G["dx_svc"].get(d, 0) + n
        salida = []
        orden = {"total": 0, "departamento": 1, "municipio": 2, "contrato": 3}
        for G in sorted(grupos.values(), key=lambda x: (orden[x["nivel"]], x["nombre"])):
            salida.append({
                "nivel": G["nivel"], "nombre": G["nombre"], "archivos": G["archivos"],
                "pacientes": len(G["pacientes"]), "pacientes_dx": len(G["pacientes_dx"]),
                # actividades["GRUPO|CUPS"] = [veces en pacientes del grupo, pacientes del grupo, veces en todos, pacientes todos]
                "actividades": {f"{gr}|{c}": [G["svc_dx"].get(f"{gr}|{c}", 0), len(G["pac_dx"].get(f"{gr}|{c}", ())),
                                              G["svc"].get(f"{gr}|{c}", 0), len(G["pac"].get(f"{gr}|{c}", ()))] for gr, c in acts},
                "pacientes_grupo": {gr: len(G["pac_grupo"].get(gr, ())) for gr in orden_g},
                "diagnosticos": {d: [len(G["dx_pac"].get(d, ())), G["dx_svc"].get(d, 0)] for d in dxcat},
            })
        for s in salida:   # prestador / municipio de cada contrato, para mostrarlo
            if s["nivel"] == "contrato":
                c = contratos.get(s["nombre"], {})
                s["prestador"], s["municipio"] = c.get("prestador", ""), c.get("municipio", "")
        return {"tipo": tipo, "anio": anio, "meses": meses, "regimen": regimen or "RS+RC",
                "catalogo": {"grupos": orden_g, **{k: cat.get(k) for k in ("actividades", "sin_codigo", "diagnosticos", "actualizado", "por")}},
                "grupos": salida, "contratos_tipo": len(contratos), "meses_datos": sorted(meses_con)}

    # ══════════════════════════════════════════ tipos sin catálogo: motores 3280, asistencial y TODOS
    def motor_de(self, tipo):
        t = tipo.upper()
        if t in self.catalogo():
            return "dx"
        if t == "TODOS":
            return "todos"
        if t.split("-")[0] in ("MD", "MDC"):   # contratos de medicamentos (incl. MD-RCV): solo medicamentos
            return "med"
        return "3280" if t in TIPOS_3280 or "RCV" in t.split("-") else "asis"

    def _archivos_contrato(self, con, contrato, anio, meses, regimen, meses_con=None):
        """RIPS del contrato en esos meses de atención; si se pasa «meses_con», anota los meses que sí trajeron RIPS."""
        carpeta = self.bot / "descargas" / "soportes" / re.sub(r"[^A-Za-z0-9._-]", "_", contrato).strip("_")
        limpio = lambda x: re.sub(r"[^A-Za-z0-9._-]", "_", str(x)).strip("_") or "sin_nombre"
        rutas = []
        for m in meses:   # mes de atención m → cápita m+1 (sin los RIPS en cero)
            a_cap, m_cap = (anio + 1, 1) if m == 12 else (anio, m + 1)
            sql = ("SELECT recepcion, regimen, fecha_recepcion FROM registros WHERE contrato=? AND periodo_anio=? "
                   "AND periodo_mes=? AND (fuente LIKE 'CONSULTAS%' OR fuente LIKE 'OTROS%') AND estado NOT LIKE 'NO VIGENTE%'")
            params = [contrato, a_cap, m_cap]
            if regimen:
                sql += " AND regimen=?"
                params.append(regimen)
            for rec, _, _ in ultimos_por_regimen(con.execute(sql, params).fetchall()):   # solo el último cargue
                enc = sorted(carpeta.glob(f"{limpio(rec)}__*"))
                if enc:
                    rutas.append(str(enc[0]))
                    if meses_con is not None:
                        meses_con.add(m)
        return rutas

    def solicitar(self, tipo, anio, meses, regimen, contratos_meta, hist, encolar=True, modalidad=""):
        """Resultado listo o, si falta calcular contratos, {'calculando': True, 'hechos', 'total'} (se calcula aparte)."""
        motor = self.motor_de(tipo)
        if motor == "dx":
            res = self.calcular(tipo, anio, meses, regimen, contratos_meta, hist)
            res["motor"] = "dx"
            return res
        t = tipo.upper()
        contratos = [c for c in contratos_meta if t == "TODOS" or tipo_contrato(c["contrato"]) == t]
        tareas, faltan, meses_con = [], [], set()
        # TODOS también clasifica con los catálogos cargados: si cambian, se recalcula
        extra = ""
        if motor == "todos" and self.ruta_cat.exists():
            extra = str(self.ruta_cat.stat().st_mtime_ns)
        with closing(sqlite3.connect(hist)) as con:
            for c in contratos:
                rutas = self._archivos_contrato(con, c["contrato"], anio, meses, regimen, meses_con)
                firma = "|".join(f"{r}:{os.stat(r).st_mtime_ns}:{os.stat(r).st_size}" for r in sorted(rutas))
                clave = hashlib.sha1(f"{motor}|{self.M.VERSIONES.get(motor, 1)}|{c['contrato']}|{firma}|{extra}".encode()).hexdigest()[:24]
                out = self.cache / f"c_{motor}_{clave}.json"
                tareas.append((c, rutas, out))
                if rutas and not out.exists():
                    faltan.append({"archivos": rutas, "out": str(out)})
        if faltan:
            if encolar:
                self._encolar(motor, faltan)
            return {"tipo": t, "motor": motor, "calculando": True, "total": len(tareas),
                    "hechos": len(tareas) - len(faltan)}
        res = self._agregar(motor, t, anio, meses, regimen, tareas, modalidad)
        res["meses_datos"] = sorted(meses_con)   # meses de atención que sí tienen RIPS radicados
        return res

    def _encolar(self, motor, tareas):
        with self._cola_lock:
            nuevas = [x for x in tareas if x["out"] not in self._en_curso]
            if not nuevas:
                return
            self._en_curso.update(x["out"] for x in nuevas)
            self._cola.append((motor, nuevas))
            self._hay.set()

    def _correr_cola(self):
        job = Path(__file__).resolve().parent / "frecuencia_job.py"
        while True:
            self._hay.wait()
            with self._cola_lock:
                if not self._cola:
                    self._hay.clear()
                    continue
                motor, tareas = self._cola.pop(0)
            spec = self.cache / f"job_{os.getpid()}_{threading.get_ident()}.json"
            try:
                spec.write_text(json.dumps({"motor": motor, "cache": str(self.cache), "tareas": tareas}), encoding="utf-8")
                r = subprocess.run([sys.executable, str(job), str(spec)], capture_output=True, text=True, timeout=3 * 3600)
                print((r.stdout or "").strip() or (r.stderr or "")[-500:], flush=True)
            except Exception as e:   # un fallo no detiene la cola
                print(f"[frecuencia] error en el cálculo: {e}", flush=True)
            finally:
                spec.unlink(missing_ok=True)
                with self._cola_lock:
                    self._en_curso.difference_update(x["out"] for x in tareas)

    def _agregar(self, motor, tipo, anio, meses, regimen, tareas, modalidad=""):
        vacio = {"act": {}, "pg": {}, "n": {}, "s": {}, "pac": 0, "arch": 0}
        modalidad = modalidad if modalidad in self.M.MODALIDADES else ""
        G, nombres, secc, errores, mods_total = {}, {}, {}, [], {}
        orden = {"contrato": 0, "municipio": 1, "departamento": 2, "total": 3}
        for c, rutas, out in tareas:
            r = json.loads(out.read_text(encoding="utf-8")) if rutas and out.exists() else vacio
            if r.get("error"):
                errores.append(f"{c['contrato']}: {r['error']}")
                r = vacio
            for k, v in r.get("n", {}).items():
                nombres.setdefault(k, v)
            for k, v in r.get("s", {}).items():
                secc.setdefault(k, v)
            # modalidad: cada código con cuántas veces vino por modalidad (para marcarlo en la fila del total)
            for mod, rm in r.get("mod", {}).items():
                for k, v in rm.get("act", {}).items():
                    acc = mods_total.setdefault(k, {}).setdefault(mod, [0] * len(v))
                    for i, x in enumerate(v):
                        acc[i] += x
            if modalidad:   # solo los registros de esa modalidad (la población de cada programa 3280 no cambia)
                rm = r.get("mod", {}).get(modalidad, {})
                r = dict(r, act=rm.get("act", {}), pg=r["pg"] if motor == "3280" else rm.get("pg", {}))
            for nivel, nombre in (("contrato", c["contrato"]), ("municipio", c.get("municipio") or "—"),
                                  ("departamento", departamento(c["contrato"])), ("total", f"Total {tipo}")):
                g = G.setdefault((nivel, nombre), {"nivel": nivel, "nombre": nombre, "act": {}, "pg": {}, "pac": 0, "arch": 0})
                for k, v in r["act"].items():
                    acc = g["act"].setdefault(k, [0] * len(v))
                    for i, x in enumerate(v):
                        acc[i] += x
                for k, n in r["pg"].items():
                    g["pg"][k] = g["pg"].get(k, 0) + n
                g["pac"] += r["pac"]
                g["arch"] += r["arch"]
                if nivel == "contrato":
                    g["prestador"], g["municipio"] = c.get("prestador", ""), c.get("municipio", "")
        total = G.get(("total", f"Total {tipo}"), {"act": {}, "pg": {}})
        cat, renombre = self._catalogo_motor(motor, total, nombres, secc)
        salida = []
        for g in sorted(G.values(), key=lambda x: (orden[x["nivel"]], x["nombre"])):
            act = {renombre(k): v for k, v in g["act"].items() if any(v)}
            pg = {renombre(k + "|").rstrip("|"): n for k, n in g["pg"].items()}
            salida.append({"nivel": g["nivel"], "nombre": g["nombre"], "archivos": g["arch"], "pacientes": g["pac"],
                           "pacientes_dx": g["pac"], "actividades": act, "pacientes_grupo": pg, "diagnosticos": {},
                           **({"prestador": g["prestador"], "municipio": g["municipio"]} if g["nivel"] == "contrato" else {})})
        mods = {renombre(k): {m: v for m, v in d.items()} for k, d in mods_total.items()}
        return {"tipo": tipo, "motor": motor, "anio": anio, "meses": meses, "regimen": regimen or "RS+RC",
                "modalidad": modalidad, "modalidades": self.M.MODALIDADES, "mods": mods,
                "catalogo": cat, "grupos": salida, "contratos_tipo": len(tareas), "errores": errores[:20]}

    def _catalogo_motor(self, motor, total, nombres, secc):
        """Catálogo para la pantalla (grupos, actividades) y función que pasa claves internas a las de pantalla."""
        M = self.M
        ahora = datetime.now().astimezone().isoformat(timespec="seconds")
        if motor == "3280":
            progs = M.PROGS_3280
            etiqueta = {p["id"]: p.get("nombre") or p["id"] for p in progs}
            etiqueta[M.OTROS_PYM] = "OTROS CÓDIGOS DE PyM REPORTADOS (no están en la matriz 3280)"
            cfg = M.ACTS_3280
            rutas = {k: re.sub(r"^[^\w]+\s*", "", v.get("label", k)) for k, v in M.CFG3280.get("rutas_diag", {}).items()}
            rutas.update({k: v.get("label", k) for k, v in M.COR3280.get("rutas", {}).items()})
            rutas["DM_HTA"] = "diabetes e hipertensión (las dos)"
            grupos, acts, info = [], [], {}
            con_datos = lambda k: any(total["act"].get(k, []))
            for p in progs:
                # solo actividades con registros (no se muestran filas vacías)
                aids = [aid for aid in p["actividades"] if aid in cfg and con_datos(f"{p['id']}|{aid}")]
                if not aids:
                    continue
                gr = etiqueta[p["id"]]
                grupos.append(gr)
                ap = M.grupos_programa(p)
                if p.get("aplica_a"):
                    info[gr] = "Pacientes con diagnóstico de: " + ", ".join(rutas.get(x, x) for x in ap)
                else:
                    info[gr] = f"Pacientes de {p.get('edad_min', 0)} a {p.get('edad_max', 200)} años" if p["id"] not in M.CVS \
                        else f"Curso de vida por edad: {p.get('edad_min', 0)}–{p.get('edad_max', 200)} años"
                for aid in aids:
                    a = cfg[aid]
                    partes = []
                    if a.get("cups"):
                        partes.append(", ".join(a["cups"]))
                    if a.get("nombres") or a.get("busqueda_nombre"):
                        partes.append("Medicamento: " + ", ".join(a.get("nombres") or a.get("busqueda_nombre")))
                    acts.append({"grupo": gr, "codigo": aid, "cups_txt": " · ".join(partes), "descripciones": [a.get("descripcion", aid)],
                                 "criterio": ARCHIVO_RIPS.get(a.get("archivo"), a.get("archivo", ""))})
            extra = sorted(((v[0], k.split("|", 1)[1]) for k, v in total["act"].items()
                            if k.startswith(M.OTROS_PYM + "|") and any(v)), reverse=True)
            if extra:
                gr = etiqueta[M.OTROS_PYM]
                grupos.append(gr)
                info[gr] = "Códigos de promoción y mantenimiento (DI, PM, PYM, I1…) que vienen en los RIPS y no tienen actividad en la matriz; se cuentan en todos los pacientes"
                for _, cod in extra:
                    acts.append({"grupo": gr, "codigo": cod, "cups_txt": cod,
                                 "descripciones": [nombres.get(cod) or "Código sin nombre en el RIPS"], "criterio": "Código reportado"})
            return ({"grupos": grupos, "actividades": acts, "sin_codigo": [], "diagnosticos": [], "grupos_info": info,
                     "actualizado": ahora, "por": "matriz 3280 (frecuencia de uso)",
                     "etiquetas": {"criterio": "Archivo RIPS", "pacientes_grupo": "Pacientes del programa",
                                   "todos": "Contar en todos los pacientes"}},
                    lambda k: etiqueta.get(k.split("|", 1)[0], k.split("|", 1)[0]) + "|" + k.split("|", 1)[1])
        # asistencial / todos: grupos = tipos de servicio (TODOS: + áreas 3280, catálogos y fuera de las matrices)
        por_tipo = {}
        for k, v in total["act"].items():
            tipo_s, cod = k.split("|", 1)
            if v[0] > 0:
                por_tipo.setdefault(tipo_s, []).append((v[0], cod))
        orden = M.ORDEN_TIPOS + M.AREAS_3280
        orden_t = {t: i for i, t in enumerate(orden)}
        # primero los tipos de servicio y las áreas 3280; después los catálogos; al final lo que no está en las matrices
        grupos = sorted(por_tipo, key=lambda t: (2 if t.startswith(M.FUERA) else 1 if t.startswith("CATÁLOGO ") else 0,
                                                 orden_t.get(t, 999), t))
        # nombres solo de las matrices: catálogo de CUPS de la EPS (asistencial) → actividad 3280 → catálogo cargado
        # (DNT…) → nombre que trae el propio RIPS (medicamentos, otros servicios) → «Sin nombre en las matrices»
        nom_cat = {}
        for c in self.catalogo().values():
            for a in c.get("actividades", []):
                if a.get("descripciones"):
                    nom_cat.setdefault(str(a["codigo"]).upper(), a["descripciones"][0])
        acts, info = [], {}
        for gr in grupos:
            if gr.startswith(M.FUERA):
                info[gr] = ("CUPS que no están en la matriz 3280, ni en la Evaluación Asistencial (asistencias, "
                            "especialidades, complementarias, PAI…), ni en los catálogos cargados; nombre oficial de la "
                            "tabla CUPS de SISPRO")
            elif gr.startswith("MATRIZ 3280"):
                info[gr] = "Códigos de la matriz 3280 que no están en la Evaluación Asistencial"
            elif gr.startswith("CATÁLOGO "):
                info[gr] = "Códigos del catálogo cargado que no están en las otras matrices"
            for _, cod in sorted(por_tipo[gr], reverse=True):
                if gr.startswith(M.FUERA):   # sin clasificar: nombre oficial de SISPRO (o el que trae el RIPS)
                    nom = (M.CUPS_NOMBRES.get(cod) or M.CUPS_NOMBRES_WEB.get(cod) or nombres.get(cod)
                           or ("Código que no existe en la tabla CUPS (SISPRO)" if cod in M.CUPS_NO_EXISTEN else M.SIN_NOMBRE))
                else:
                    nom = (M.CUPS_NOMBRES.get(cod) or M.NOMBRE_CUPS.get(cod) or nom_cat.get(cod) or nombres.get(cod)
                           or NOMBRES_SECCION.get(cod) or ("Medicamento sin nombre en el RIPS" if gr == "MEDICAMENTOS" else M.SIN_NOMBRE))
                acts.append({"grupo": gr, "codigo": cod, "descripciones": [nom], "criterio": secc.get(cod, "")})
        return ({"grupos": grupos, "actividades": acts, "sin_codigo": [], "diagnosticos": [], "grupos_info": info,
                 "actualizado": ahora, "por": {"asis": "Evaluación Asistencial", "med": "solo medicamentos"}.get(motor, "todos los RIPS"),
                 "etiquetas": {"criterio": "Archivo RIPS" if motor == "todos" else None,
                               "pacientes_grupo": "Pacientes con medicamentos" if motor == "med" else "Pacientes atendidos en el tipo de servicio",
                               "todos": None, "veces": "unid." if motor == "med" else None}},
                lambda k: k)
