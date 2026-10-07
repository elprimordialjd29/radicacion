"""
Análisis de facturas duplicadas o sospechosas entre radicaciones VIGENTES (estado Radicado),
usando los soportes RIPS descargados del SIE.

Criterios:
  A. Mismo número de factura radicado en más de una recepción del contrato  → CRÍTICA
  B. Mismo contrato + régimen + periodo con más de una radicación            → ALTA / MEDIA
  C. Dos radicaciones del contrato con ≥ 80 % de servicios idénticos         → CRÍTICA
Para cada par se mide: usuarios en común, servicios idénticos (mismo paciente, código y fecha)
y diferencia de valor.
"""
import collections
import re
import sqlite3
from pathlib import Path

import rips_json as R

BASE = Path(__file__).resolve().parent
SECCIONES = ("CONSULTAS", "PROCEDIMIENTOS", "MEDICAMENTOS", "OTROS", "URGENCIAS", "HOSPITALIZACION")


def _archivo(contrato, recepcion):
    carpeta = BASE / "descargas" / "soportes" / re.sub(r"[^A-Za-z0-9._-]", "_", str(contrato))
    f = sorted(carpeta.glob(f"{re.sub(r'[^A-Za-z0-9._-]', '_', str(recepcion))}__*"))
    return f[0] if f else None


def _leer(f):
    fac, nit, usuarios, serv = None, None, set(), {}
    sec = R.leer_plano(R.leer_archivo(f))
    if sec.get("FACTURAS"):
        c = R._campos(sec["FACTURAS"][0])
        nit, fac = (c + [None, None])[:2]
    for l in sec.get("USUARIOS", []):
        c = R._campos(l)
        if len(c) > 1:
            usuarios.add((c[0], c[1]))
    for k in SECCIONES:
        for l in sec.get(k, []):
            c = R._campos(l)
            serv[(k,) + tuple(c[1:])] = c          # clave sin el número de factura
    return fac, nit, usuarios, serv


def analizar(db_path=None):
    db = sqlite3.connect(db_path or BASE / "historial.db")
    filas = db.execute("""SELECT contrato, recepcion, regimen, valor, periodo_anio, periodo_mes, fecha_recepcion,
                                 radicacion, fuente, fecha_min, fecha_max
                          FROM registros WHERE estado NOT LIKE 'NO VIGENTE%'""").fetchall()
    db.close()
    info = {}
    for con, rec, rg, val, a, m, fr, rad, fu, fmin, fmax in filas:
        f = _archivo(con, rec)
        fac, nit, us, sv = _leer(f) if f else (None, None, set(), {})
        info[str(rec)] = dict(contrato=con, recepcion=str(rec), regimen=rg or "", valor=val or 0, anio=a, mes=m,
                              fecha_recepcion=fr or "", radicacion=rad or "", fuente=fu or "", fecha_min=fmin or "",
                              fecha_max=fmax or "", factura=fac, nit=nit, usuarios=us, servicios=sv)

    pares = {}

    def par(a, b, criterio):
        k = tuple(sorted((a["recepcion"], b["recepcion"])))
        if k not in pares:
            uc = len(a["usuarios"] & b["usuarios"])
            sc = set(a["servicios"]) & set(b["servicios"])
            base_u = max(min(len(a["usuarios"]), len(b["usuarios"])), 1)
            base_s = max(min(len(a["servicios"]), len(b["servicios"])), 1)
            dif = abs(a["valor"] - b["valor"]) / max(a["valor"], b["valor"], 1) * 100
            pares[k] = dict(a=a, b=b, criterios=set(), usuarios_comun=uc, pct_usuarios=round(uc / base_u * 100, 1),
                            servicios_identicos=len(sc), pct_servicios=round(len(sc) / base_s * 100, 1),
                            dif_valor_pct=round(dif, 3), identicos=sc)
        pares[k]["criterios"].add(criterio)

    por_fac = collections.defaultdict(list)
    por_per = collections.defaultdict(list)
    por_con = collections.defaultdict(list)
    for x in info.values():
        if x["factura"]:
            por_fac[(x["contrato"], x["factura"])].append(x)
        if x["mes"]:
            por_per[(x["contrato"], x["regimen"], x["anio"], x["mes"])].append(x)
        if x["servicios"]:
            por_con[(x["contrato"], x["regimen"])].append(x)
    for v in por_fac.values():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                par(v[i], v[j], "Mismo número de factura")
    for v in por_per.values():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                par(v[i], v[j], "Mismo contrato, régimen y periodo")
    for v in por_con.values():
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                a, b = v[i], v[j]
                comun = len(set(a["servicios"]) & set(b["servicios"]))
                if comun / max(min(len(a["servicios"]), len(b["servicios"])), 1) >= 0.8:
                    par(a, b, "Servicios idénticos (≥80 %)")

    salida = []
    for p in pares.values():
        crit = p["criterios"]
        if "Mismo número de factura" in crit or p["pct_servicios"] >= 80:
            nivel, nombre = 3, "Crítica"
        elif p["pct_servicios"] >= 30 or (p["pct_usuarios"] >= 90 and p["dif_valor_pct"] <= 0.5):
            nivel, nombre = 2, "Alta"
        else:
            nivel, nombre = 1, "Media"
        if nivel == 3 or p["pct_servicios"] >= 30:
            lectura = "Muy probable doble cobro: las facturas repiten las mismas atenciones."
        elif p["pct_usuarios"] >= 90 and p["pct_servicios"] < 5:
            lectura = "Mismos usuarios con atenciones distintas: posible factura partida en dos para el mismo mes."
        else:
            lectura = "Dos radicaciones para el mismo periodo: verificar si una corresponde a otro mes o es un ajuste."
        a, b = p["a"], p["b"]
        salida.append(dict(
            nivel=nivel, prioridad=nombre, criterios=sorted(crit), lectura=lectura,
            contrato=a["contrato"], regimen=a["regimen"], periodo=f"{a['anio']}-{(a['mes'] or 0):02d}",
            usuarios_comun=p["usuarios_comun"], pct_usuarios=p["pct_usuarios"],
            servicios_identicos=p["servicios_identicos"], pct_servicios=p["pct_servicios"], dif_valor_pct=p["dif_valor_pct"],
            valor_en_riesgo=min(a["valor"], b["valor"]),
            facturas=[{k: x[k] for k in ("recepcion", "factura", "nit", "regimen", "valor", "fecha_recepcion", "radicacion",
                                         "anio", "mes", "fecha_min", "fecha_max", "fuente")}
                      | {"usuarios": len(x["usuarios"]), "servicios": len(x["servicios"])} for x in (a, b)],
            _identicos=[(k[0], p["a"]["servicios"][k]) for k in sorted(p["identicos"])],
        ))
    salida.sort(key=lambda d: (-d["nivel"], -d["valor_en_riesgo"]))
    resumen = dict(radicaciones=len(info), con_factura=sum(1 for x in info.values() if x["factura"]),
                   pares=len(salida), criticos=sum(1 for d in salida if d["nivel"] == 3),
                   altos=sum(1 for d in salida if d["nivel"] == 2),
                   valor_en_riesgo=sum(d["valor_en_riesgo"] for d in salida if d["nivel"] >= 2))
    return resumen, salida


def a_excel(resumen, pares, ruta, prestadores=None):
    """Excel con el resumen, los pares sospechosos y el detalle de servicios repetidos
    (contiene datos de pacientes: uso interno de auditoría)."""
    import pandas as pd
    prestadores = prestadores or {}
    filas = []
    for i, d in enumerate(pares, 1):
        a, b = d["facturas"]
        filas.append({
            "#": i, "Prioridad": d["prioridad"], "Contrato": d["contrato"], "Prestador": prestadores.get(d["contrato"], ""),
            "Régimen": d["regimen"], "Periodo": d["periodo"], "Criterios": "; ".join(d["criterios"]), "Lectura": d["lectura"],
            "Factura A": a["factura"], "Recepción A": a["recepcion"], "Radicación A": a["radicacion"],
            "Fecha recepción A": a["fecha_recepcion"], "Valor A": a["valor"], "Atención A": f"{a['fecha_min']} a {a['fecha_max']}",
            "Usuarios A": a["usuarios"], "Servicios A": a["servicios"],
            "Factura B": b["factura"], "Recepción B": b["recepcion"], "Radicación B": b["radicacion"],
            "Fecha recepción B": b["fecha_recepcion"], "Valor B": b["valor"], "Atención B": f"{b['fecha_min']} a {b['fecha_max']}",
            "Usuarios B": b["usuarios"], "Servicios B": b["servicios"],
            "Usuarios en común": d["usuarios_comun"], "% usuarios en común": d["pct_usuarios"],
            "Servicios idénticos": d["servicios_identicos"], "% servicios idénticos": d["pct_servicios"],
            "Diferencia de valor %": d["dif_valor_pct"], "Valor en riesgo": d["valor_en_riesgo"],
        })
    det = []
    for i, d in enumerate(pares, 1):
        a, b = d["facturas"]
        for seccion, c in d["_identicos"]:
            det.append({"#": i, "Contrato": d["contrato"], "Factura A": a["factura"], "Factura B": b["factura"],
                        "Sección": seccion, "Campos del servicio (orden RIPS)": ", ".join(c)})
    res = pd.DataFrame([
        ("Radicaciones vigentes analizadas", resumen["radicaciones"]),
        ("Con número de factura en el soporte", resumen["con_factura"]),
        ("Pares sospechosos", resumen["pares"]),
        ("Prioridad crítica", resumen["criticos"]), ("Prioridad alta", resumen["altos"]),
        ("Valor en riesgo (crítica + alta)", resumen["valor_en_riesgo"]),
        ("Criterios", "A) mismo número de factura · B) mismo contrato+régimen+periodo · C) ≥80 % servicios idénticos"),
        ("Fuente", "SIE Dusakawi · Consulta Recepción (Radicado) + soportes RIPS (ARCHIVO-FACTURAS/USUARIOS/servicios)"),
        ("Aviso", "La hoja 'Servicios repetidos' contiene datos de pacientes: uso interno de auditoría."),
    ], columns=["Indicador", "Valor"])
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        res.to_excel(xw, sheet_name="Resumen", index=False)
        pd.DataFrame(filas).to_excel(xw, sheet_name="Facturas sospechosas", index=False)
        pd.DataFrame(det or [{"Info": "Sin servicios repetidos"}]).to_excel(xw, sheet_name="Servicios repetidos", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ancho = max(len(str(c.value or "")) for c in col[:100])
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 60)
            ws.freeze_panes = "A2"
    return ruta
