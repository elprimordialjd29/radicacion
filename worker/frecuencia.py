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
import re
import sqlite3
import sys
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


def departamento(contrato):
    m = re.match(r"^[A-Z]+-(\d{2})\d{3}-", contrato or "")
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
        with closing(sqlite3.connect(hist)) as con:
            for contrato, meta in contratos.items():
                for m in meses:   # mes de atención m → cápita m+1
                    a_cap, m_cap = (anio + 1, 1) if m == 12 else (anio, m + 1)
                    sql = ("SELECT recepcion, regimen FROM registros WHERE contrato=? AND periodo_anio=? AND periodo_mes=? "
                           "AND (fuente LIKE 'CONSULTAS%' OR fuente LIKE 'OTROS%') AND estado NOT LIKE 'NO VIGENTE%'")
                    params = [contrato, a_cap, m_cap]
                    if regimen:
                        sql += " AND regimen=?"
                        params.append(regimen)
                    for rec, reg in con.execute(sql, params).fetchall():
                        enc = sorted((carpeta / limpio(contrato)).glob(f"{limpio(rec)}__*"))
                        if not enc:
                            continue
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
                "grupos": salida, "contratos_tipo": len(contratos)}
