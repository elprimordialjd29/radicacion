"""Motores de frecuencia de uso por tipo de contrato (se usan desde frecuencia_job.py, en un proceso aparte).

- «asis»  (ASE, ASB, EB, MD, MDC, CMP, PAI): igual que la Evaluación Cápita Asistencial
  (repo evaluacion-capita-asistencial, App.tsx): cada CUPS va a su tipo de servicio según el mapa fijo
  (config/asistencial_cups.json); consultas/procedimientos cuentan cada línea con un CUPS conocido;
  medicamentos cuentan la cantidad (sin repetir paciente+código+fecha, sin oxígeno); otros servicios
  cuentan la cantidad de los códigos de 6 caracteres; cada línea de urgencias = URGENCIAS BC.
- «3280»  (PMS, RCV): programas y actividades de la matriz 3280 (config/res3280_cups.json, repo
  evaluador-3280), versión SENCILLA pedida por el usuario: sin finalidad ni valor único. Cada registro
  con un CUPS de la actividad (o, en medicamentos, con el nombre buscado) cuenta en los pacientes del
  programa: curso de vida por edad a la última fecha de atención del RIPS y rutas por diagnóstico.
- «todos» (TODOS): todos los códigos reportados en el RIPS, con su tipo de servicio (mapa asistencial
  o, si no está, el archivo RIPS donde vino).

Cada RIPS se resume UNA vez (caché por archivo); el resultado de un contrato junta sus archivos.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parent / "bot"))
import rips_json  # noqa: E402

VERSION = 1
CFG3280 = json.loads((DIR / "config" / "res3280_cups.json").read_text(encoding="utf-8"))
ASIS = json.loads((DIR / "config" / "asistencial_cups.json").read_text(encoding="utf-8"))
CUPS_TIPO = {c: x["tipo"] for x in ASIS["mapa"] for c in x["cups"]}
ORDEN_TIPOS = [x["tipo"] for x in ASIS["mapa"]] + ["MEDICAMENTOS", "URGENCIAS BC", "OTROS SERVICIOS"]

# descripciones conocidas de CUPS (para mostrar algo en consultas/procedimientos, que el RIPS no nombra)
NOMBRE_CUPS = {}
for _a in CFG3280["actividades_base"].values():
    for _c in _a.get("cups", []):
        NOMBRE_CUPS.setdefault(str(_c).upper(), _a.get("descripcion", ""))


def _leer(ruta, codificacion):
    return Path(ruta).read_bytes().decode(codificacion, errors="replace")


# ══════════════════════════════════════════════════════════════════ ASISTENCIAL
_RE_AT_CAMPO = re.compile(r"(?:^|[,|\t])(\d{3,4}T\d{2})(?:[,|\t]|$)", re.I)
_RE_DOC = re.compile(r"^(CC|TI|RC|CE|PA|PE|CN|MS)$", re.I)


def _normalizar_id(v):
    x = str(v or "").strip()
    x = re.sub(r"^(CC|TI|RC|CE|PA|PE|CN|MS)[-\s]*", "", x, flags=re.I)
    return re.sub(r"[^0-9A-Za-z]", "", x).upper()


def _parse_int(s):
    """parseInt(s, 10) de JavaScript: el entero al inicio del texto, o None."""
    m = re.match(r"\s*([+-]?\d+)", str(s or ""))
    return int(m.group(1)) if m else None


def _fecha_linea(l):
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b|\b(\d{2}/\d{2}/\d{4})\b", l, re.A)
    return (m.group(1) or m.group(2)) if m else ""


def _paciente_at(partes):
    k = next((i for i, p in enumerate(partes) if _RE_DOC.match(p.strip())), -1)
    if k >= 0 and k + 1 < len(partes) and partes[k + 1]:
        pid = _normalizar_id(partes[k + 1].strip())
        if pid and len(pid) >= 3:
            return pid
    hallado = next((p for p in partes if re.fullmatch(r"\d{6,11}", p.strip())), "")
    return _normalizar_id(hallado) or "SIN_ID"


def registros_asistencial(texto):
    """Lista de (cups, paciente, tipo, nombre), igual que el procesamiento TXT de la Evaluación Asistencial."""
    get_tipo = CUPS_TIPO.get
    lineas = re.split(r"\r?\n", texto)
    regs, at_lineas = [], set()
    # pre-búsqueda de códigos AT (traslados, p. ej. 601T01) en todo el archivo
    for li, raw in enumerate(lineas):
        if not raw or not _RE_AT_CAMPO.search(raw):
            continue
        l = raw.strip()
        partes = [x.strip() for x in l.split("\t")] if "\t" in l else [re.sub(r"[|]$", "", x.strip()) for x in l.split(",")]
        if len(partes) < 5 or re.match(r"^bill|^productid|^tipo|^clientid|^nombre", partes[0], re.I):
            continue
        cups_at = next((p.strip().upper() for p in partes if re.fullmatch(r"\d{3,4}T\d{2}", p.strip(), re.I)), "")
        if not cups_at:
            continue
        k = next((i for i, p in enumerate(partes) if p.strip().upper() == cups_at), -1)
        nombre = partes[k + 1].strip() if k >= 0 and k + 1 < len(partes) and len(partes[k + 1].strip()) > 3 else "TRASLADO ASISTENCIAL"
        cantidad = 1
        for pi in range(k + 2, len(partes)):
            v = _parse_int(partes[pi])
            if v is not None and 0 < v < 200:
                cantidad = v
                break
        pac = _paciente_at(partes)
        if pac == "SIN_ID" or len(pac) < 3:
            continue
        at_lineas.add(li)
        regs.extend([(cups_at, pac, get_tipo(cups_at) or "TAB", nombre)] * cantidad)

    seccion, en_at, en_urg, med_vistos = "", False, False, set()
    for li, raw in enumerate(lineas):
        if li in at_lineas:
            continue
        l = raw.strip()
        if not l:
            continue
        U = l.upper()
        if "ARCHIVO-RIPS-AT" in U or "OTROS SERVICIOS" in U or (re.search(r"RIPS.*AT\b|^.*-\s*AT\s*-.*$", U, re.A) and "," not in l):
            seccion, en_at, en_urg = "SERVICIOS", True, False
            continue
        if "ARCHIVO-RIPS-US" in U or ("USUARIOS" in U and ("*" in U or "°" in U or "-" in U)):
            seccion, en_at, en_urg = "USUARIOS", False, False
            continue
        if "ARCHIVO-RIPS-AM" in U or "MEDICAMENTOS" in U:
            seccion, en_at, en_urg = "MEDICAMENTOS", False, False
            continue
        if "ARCHIVO-URGENCIAS" in U or "ARCHIVO-RIPS-AU" in U:
            en_urg, en_at, seccion = not en_urg, False, "URGENCIAS_TXT"
            continue
        if any(t in U for t in ("ARCHIVO-RIPS-CT", "ARCHIVO-RIPS-AC", "ARCHIVO-RIPS-AP", "CONSULTAS", "PROCEDIMIENTOS")):
            seccion, en_at, en_urg = "SERVICIOS", False, False
            continue
        if "\t" in l and len(l.split("\t")) >= 3:
            partes = [x.strip() for x in l.split("\t")]
        elif "," in l and l.count(",") >= 3:
            partes = [re.sub(r"[|]$", "", x.strip()) for x in l.split(",")]
        elif "|" in l:
            partes = [x.strip() for x in l.split("|")]
        else:
            continue
        if len(partes) < 2:
            continue
        if seccion not in ("USUARIOS", "MEDICAMENTOS"):
            if re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", l) and re.search(r"\b(M|F)\b", l, re.I | re.A):
                seccion = "USUARIOS"
        if "USUARIOS" in seccion:
            continue
        if seccion == "MEDICAMENTOS":
            mp = [s.strip() for s in re.sub(r"\|+$", "", l).split(",")]
            if len(mp) < 17:
                continue
            pac = _normalizar_id(mp[2])
            if not pac or len(pac) < 3:
                continue
            cod = (mp[10] or "MEDICAM").strip() or "MEDICAM"
            nombre = (mp[11] or "Medicamento").strip()
            if re.search(r"OXIGENO|OXIGEN|GAS\s+MED|OXYGEN", nombre, re.I):
                continue
            fecha = (mp[6] or "").split(" ")[0].split("T")[0] or _fecha_linea(l)
            cantidad = max(1, _parse_int(mp[16] or "1") or 1)
            clave = f"{pac}|{cod}|{fecha}"
            if clave in med_vistos:
                continue
            med_vistos.add(clave)
            regs.extend([(cod, pac, "MEDICAMENTOS", nombre)] * cantidad)
            continue
        if en_urg:
            up = [x.strip() for x in re.sub(r"\|+$", "", l).split(",")]
            if len(up) < 3:
                continue
            pid = _normalizar_id(up[2] or "")
            if pid and len(pid) >= 3:
                regs.append(("URGBC", pid, "URGENCIAS BC", "Urgencias Baja Complejidad"))
            continue
        if en_at:
            if len(partes) < 4 or re.match(r"^bill|^productid|^tipo|^clientid", partes[0], re.I):
                continue
            cups, k = "", -1
            for pi, p in enumerate(partes):
                v = p.strip().upper()
                if re.fullmatch(r"[0-9][0-9A-Z]{5}", v):
                    cups, k = v, pi
                    break
            if not cups:
                continue
            nombre = partes[k + 1].strip() if k + 1 < len(partes) and partes[k + 1] else "OTROS SERVICIOS"
            cantidad = 1
            for pi in range(k + 2, len(partes)):
                v = _parse_int(partes[pi])
                if v is not None and 0 < v < 1000:
                    cantidad = v
                    break
            pac = _paciente_at(partes)
            if pac == "SIN_ID" or len(pac) < 3:
                continue
            regs.extend([(cups, pac, get_tipo(cups) or "OTROS SERVICIOS", nombre)] * cantidad)
            continue
        m = re.search(r"\b([0-9][0-9A-Za-z]{5})\b", l, re.A)
        if not m:
            continue
        cups = m.group(1).upper()
        es_at = re.fullmatch(r"\d{3,4}[A-Z]\d{2}", cups)
        if cups not in CUPS_TIPO and not es_at:
            continue
        if es_at:
            if re.match(r"^bill|^productid|^tipo|^clientid", partes[0], re.I):
                continue
            k = next((i for i, p in enumerate(partes) if p.strip().upper() == cups), -1)
            nombre = partes[k + 1].strip() if k >= 0 and k + 1 < len(partes) and partes[k + 1] else "TRASLADO / OTRO SERVICIO"
            cantidad = 1
            for pi in range((k if k >= 0 else 0) + 2, len(partes)):
                v = _parse_int(partes[pi])
                if v is not None and 0 < v < 1000:
                    cantidad = v
                    break
            pac = _paciente_at(partes)
            if pac == "SIN_ID" or len(pac) < 3:
                continue
            regs.extend([(cups, pac, get_tipo(cups) or "OTROS SERVICIOS", nombre)] * cantidad)
            continue
        tipo = get_tipo(cups)
        if not tipo:
            continue
        mp_ = re.search(r"\b(?:CC|TI|RC|CE|PA|PE|CN|MS)-?\d{4,15}\b|\b\d{6,15}\b", l, re.A)
        pac = _normalizar_id(mp_.group(0) if mp_ else "SIN_ID") or "SIN_ID"
        regs.append((cups, pac, tipo, ""))
    return regs


def resumen_asistencial(ruta):
    """{'t': {tipo: {cups: {paciente: n}}}, 'n': {cups: nombre}} de un soporte."""
    texto = _leer(ruta, "utf-8")   # la Evaluación Asistencial lee el TXT como UTF-8
    t, n = {}, {}
    for cups, pac, tipo, nombre in registros_asistencial(texto):
        d = t.setdefault(tipo, {}).setdefault(cups, {})
        d[pac] = d.get(pac, 0) + 1
        if nombre and cups not in n:
            n[cups] = nombre
    return {"t": t, "n": n}


# ══════════════════════════════════════════════════════════════════ TODOS
_SECCION_TODOS = {"CONSULTAS": "Consultas", "PROCEDIMIENTOS": "Procedimientos", "MEDICAMENTOS": "Medicamentos",
                  "OTROS": "Otros servicios", "URGENCIAS": "Urgencias", "HOSPITALIZACION": "Hospitalización"}
_TIPO_POR_SECCION = {"Consultas": "CONSULTAS (otros códigos)", "Procedimientos": "PROCEDIMIENTOS (otros códigos)",
                     "Medicamentos": "MEDICAMENTOS", "Otros servicios": "OTROS SERVICIOS", "Urgencias": "URGENCIAS",
                     "Hospitalización": "HOSPITALIZACIÓN"}
_CAMPO_COD = {"CONSULTAS": "codConsulta", "PROCEDIMIENTOS": "codProcedimiento", "MEDICAMENTOS": "codTecnologiaSalud",
              "OTROS": "codTecnologiaSalud"}


def resumen_todos(ruta):
    """{'c': {codigo: {paciente: n}}, 's': {codigo: sección}, 'n': {codigo: nombre}}: cada registro del RIPS."""
    sec = rips_json.leer_plano(rips_json.leer_archivo(ruta))
    c, s, n = {}, {}, {}
    for nombre_sec, etiqueta in _SECCION_TODOS.items():
        lineas = sec.get(nombre_sec, [])
        if not lineas or nombre_sec not in rips_json.SERVICIOS:
            continue
        _, campos, campo_texto = rips_json.SERVICIOS[nombre_sec]
        nombres = ["_f", "_t", "_d"] + campos
        for l in lineas:
            reg = dict(zip(nombres, rips_json._ajustar(rips_json._campos(l), 3 + len(campos), campo_texto, nombres)))
            pac = f"{reg['_t']}{reg['_d']}"
            campo = _CAMPO_COD.get(nombre_sec)
            cod = re.sub(r"\s+", "", str(reg.get(campo) or "")).upper() if campo else nombre_sec
            if not cod:
                continue
            d = c.setdefault(cod, {})
            d[pac] = d.get(pac, 0) + 1
            s.setdefault(cod, etiqueta)
            nom = (reg.get("nomTecnologiaSalud") or "").strip()
            if nom and cod not in n:
                n[cod] = nom
    return {"c": c, "s": s, "n": n}


# ══════════════════════════════════════════════════════════════════ 3280 (sencillo)
CV = CFG3280["cursos_de_vida"]
CVS = {cv["id"] for cv in CV}
EDAD_CV = {"PRIMERA_INFANCIA": (0, 5), "INFANCIA": (6, 11), "ADOLESCENCIA": (12, 17), "JOVENES": (18, 28),
           "ADULTEZ": (29, 59), "VEJEZ": (60, 200)}
RUTAS = {k: (set(v.get("exact", [])), list(v.get("prefix", []))) for k, v in CFG3280.get("rutas_diag", {}).items()}


def grupos_programa(prog):
    """Grupos de pacientes a los que aplica un programa (igual que /api/preeval del evaluador)."""
    if prog.get("aplica_a"):
        return list(prog["aplica_a"])
    if prog["id"] in CVS:
        return [prog["id"]]
    mn, mx = prog.get("edad_min", 0), prog.get("edad_max", 200)
    return [g for g, (a, b) in EDAD_CV.items() if a <= mx and b >= mn]


def _parsear_3280(texto):
    """Port de _parsearRipsTxt del evaluador 3280."""
    raw, sec = {}, None
    for l in texto.replace("\r", "").split("\n"):
        l = re.sub(r"\|+$", "", l).strip()
        if l.startswith("°---- ARCHIVO-") and l.endswith("----°"):
            n = l.replace("°---- ARCHIVO-", "", 1).replace(" ----°", "", 1).strip()
            if n not in raw:
                raw[n], sec = [], n
            else:
                sec = None
        elif sec and l and not l.startswith("°"):
            raw[sec].append(l)

    def c(l, i):
        p = l.split(",")
        return p[i].strip() if i < len(p) else ""

    def cc(l, i):
        return c(l, i).split("|")[0].upper()

    r = {}
    r["usuarios"] = [{"tipo": c(l, 0), "num": c(l, 1), "fnac": c(l, 3)} for l in raw.get("USUARIOS", []) if c(l, 1)]
    r["consultas"] = [{"tipo": c(l, 1), "num": c(l, 2), "fecha": c(l, 4)[:10], "cups": cc(l, 6), "dx": c(l, 12).upper()}
                      for l in raw.get("CONSULTAS", []) if c(l, 2) and cc(l, 6)]
    r["procedimientos"] = [{"tipo": c(l, 1), "num": c(l, 2), "fecha": c(l, 4)[:10], "cups": cc(l, 7), "dx": c(l, 15).upper()}
                           for l in raw.get("PROCEDIMIENTOS", []) if c(l, 2) and cc(l, 7)]
    r["medicamentos"] = [{"tipo": c(l, 1), "num": c(l, 2), "fecha": c(l, 6)[:10], "cups": cc(l, 10), "nombre": c(l, 11).upper()}
                         for l in raw.get("MEDICAMENTOS", []) if c(l, 2)]
    r["otrosServicios"] = [{"tipo": c(l, 1), "num": c(l, 2), "fecha": c(l, 6)[:10], "cups": cc(l, 8)}
                           for l in raw.get("OTROS SERVICIOS", []) if c(l, 2) and cc(l, 8)]
    return r


def _fecha_iso(f):
    f = (f or "").strip()
    if "/" in f:
        p = f.split("/")
        return f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}" if len(p) == 3 else ""
    if re.fullmatch(r"\d{8}", f):
        return f"{f[:4]}-{f[4:6]}-{f[6:8]}"
    return f[:10]


def _edad(fnac, ref):
    try:
        yn, mn, dn = (int(x) for x in fnac.split("-"))
        yr, mr, dr = (int(x) for x in ref.split("-"))
    except (ValueError, AttributeError):
        return None
    e = yr - yn - (1 if (mr, dr) < (mn, dn) else 0)
    return max(e, 0)


def _grupo_cv(edad):
    if edad is None:
        return None
    for g, (a, b) in EDAD_CV.items():
        if a <= edad <= b:
            return g
    return None


def _rutas(dx):
    out = []
    for g, (exactos, prefijos) in RUTAS.items():
        if dx in exactos or any(dx.startswith(p) for p in prefijos):
            out.append(g)
    return out


def resumen_3280(ruta):
    """{'a': {'PROG|ACT': {paciente: n}}, 't': {ACT: {paciente: n}}, 'g': {PROG: [pacientes]}} de un soporte."""
    A = _parsear_3280(_leer(ruta, "cp1252"))
    servicios = ("consultas", "procedimientos", "medicamentos", "otrosServicios")
    ref = max((r["fecha"] for k in servicios for r in A[k] if r["fecha"]), default="")
    grupos = {}   # paciente → grupos (curso de vida por edad + rutas por diagnóstico)
    for u in A["usuarios"]:
        g = _grupo_cv(_edad(_fecha_iso(u["fnac"]), ref))
        if g:
            grupos.setdefault(u["num"], set()).add(g)
    for k in ("consultas", "procedimientos"):
        for r in A[k]:
            for g in _rutas(r["dx"]):
                grupos.setdefault(r["num"], set()).add(g)
    acts, todos, pacs_prog = {}, {}, {}
    progs = [(p, set(grupos_programa(p))) for p in CFG3280["programas"]]
    for p, aplica in progs:
        pacs_prog[p["id"]] = sorted(num for num, gs in grupos.items() if gs & aplica)
    cfg = CFG3280["actividades_base"]
    for aid, act in cfg.items():
        cups = {str(x).strip().upper() for x in act.get("cups", [])}
        kws = [str(x).strip().upper() for x in (act.get("nombres") or act.get("busqueda_nombre") or [])]
        if not cups and not kws:
            continue

        def coincide(r):
            return (r["cups"] in cups) if cups else any(kw in r.get("nombre", "") for kw in kws)

        filas = [r for r in A.get(act["archivo"], []) if coincide(r)]
        if not filas and act.get("archivo_fallback"):
            filas = [r for r in A.get(act["archivo_fallback"], []) if coincide(r)]
        if not filas:
            continue
        d = todos.setdefault(aid, {})
        for r in filas:
            d[r["num"]] = d.get(r["num"], 0) + 1
    for p, aplica in progs:
        for aid in p["actividades"]:
            if aid not in todos:
                continue
            d = {num: n for num, n in todos[aid].items() if grupos.get(num, set()) & aplica}
            if d:
                acts[f"{p['id']}|{aid}"] = d
    return {"a": acts, "t": todos, "g": {k: v for k, v in pacs_prog.items() if v}}


# ══════════════════════════════════════════════════════════════════ por contrato
RESUMIDORES = {"asis": resumen_asistencial, "todos": resumen_todos, "3280": resumen_3280}


def resumen_archivo(motor, ruta, cache_dir):
    st = Path(ruta).stat()
    clave = hashlib.sha1(f"{motor}|{VERSION}|{ruta}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:24]
    arch = Path(cache_dir) / f"r_{motor}_{clave}.json"
    if arch.exists():
        return json.loads(arch.read_text(encoding="utf-8"))
    res = RESUMIDORES[motor](ruta)
    tmp = arch.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, separators=(",", ":")), encoding="utf-8")
    tmp.replace(arch)
    return res


def _sumar(destino, origen):
    for pac, n in origen.items():
        destino[pac] = destino.get(pac, 0) + n


def resultado_contrato(motor, archivos, cache_dir):
    """Junta los resúmenes de los archivos del contrato.
    act[clave] = [veces, pacientes] (asis/todos) o [veces grupo, pacientes grupo, veces todos, pacientes todos] (3280);
    pg[grupo] = pacientes distintos del grupo; n = nombres; s = sección de cada código."""
    act, pg, nombres, secc, pacientes = {}, {}, {}, {}, set()
    if motor == "3280":
        a, t, g = {}, {}, {}
        for ruta in archivos:
            r = resumen_archivo(motor, ruta, cache_dir)
            for k, d in r["a"].items():
                _sumar(a.setdefault(k, {}), d)
            for k, d in r["t"].items():
                _sumar(t.setdefault(k, {}), d)
            for k, lst in r["g"].items():
                g.setdefault(k, set()).update(lst)
                pacientes.update(lst)
        for k, d in a.items():
            aid = k.split("|", 1)[1]
            tt = t.get(aid, {})
            act[k] = [sum(d.values()), len(d), sum(tt.values()), len(tt)]
        # actividades sin pacientes del grupo, pero reportadas en otros pacientes
        for p in CFG3280["programas"]:
            for aid in p["actividades"]:
                k = f"{p['id']}|{aid}"
                if k not in act and aid in t:
                    act[k] = [0, 0, sum(t[aid].values()), len(t[aid])]
        pg = {k: len(v) for k, v in g.items()}
    else:
        por_tipo, cods = {}, {}
        for ruta in archivos:
            r = resumen_archivo(motor, ruta, cache_dir)
            if motor == "asis":
                for tipo, d in r["t"].items():
                    for cod, pacs in d.items():
                        _sumar(cods.setdefault(f"{tipo}|{cod}", {}), pacs)
                nombres.update({k: v for k, v in r["n"].items() if k not in nombres})
            else:
                for cod, pacs in r["c"].items():
                    sec = r["s"].get(cod, "")
                    tipo = CUPS_TIPO.get(cod) or _TIPO_POR_SECCION.get(sec, "OTROS")
                    _sumar(cods.setdefault(f"{tipo}|{cod}", {}), pacs)
                    secc.setdefault(cod, sec)
                nombres.update({k: v for k, v in r["n"].items() if k not in nombres})
        for k, d in cods.items():
            act[k] = [sum(d.values()), len(d)]
            tipo = k.split("|", 1)[0]
            por_tipo.setdefault(tipo, set()).update(d)
            pacientes.update(d)
        pg = {k: len(v) for k, v in por_tipo.items()}
    return {"act": act, "pg": pg, "n": nombres, "s": secc, "pac": len(pacientes), "arch": len(archivos)}
