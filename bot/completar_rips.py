"""Completa en el historial los datos internos del RIPS (n.º de factura, usuarios, servicios,
meses de atención) leyendo los soportes ya descargados. Se puede correr las veces que sea."""
import re, sqlite3, sys
from collections import Counter
from pathlib import Path
import rips_json as R
import sie_bot as b

con = b.abrir_db()   # agrega las columnas nuevas si faltan
filas = con.execute("SELECT clave, contrato, recepcion FROM registros").fetchall()
n = 0
for clave, contrato, rec in filas:
    carpeta = b.BASE / "descargas" / "soportes" / re.sub(r"[^A-Za-z0-9._-]", "_", str(contrato))
    f = sorted(carpeta.glob(f"{re.sub(r'[^A-Za-z0-9._-]', '_', str(rec))}__*"))
    if not f:
        continue
    sec = R.leer_plano(R.leer_archivo(f[0]))
    fac = ""
    if sec.get("FACTURAS"):
        c = R._campos(sec["FACTURAS"][0]); fac = c[1] if len(c) > 1 else ""
    # misma regla que el bot: fechas de CONSULTAS (o de los demás servicios si no hay consultas)
    lineas = sec.get("CONSULTAS") or [l for k, v in sec.items() if k not in ("USUARIOS", "FACTURAS", "CONSULTAS") for l in v]
    meses = Counter((a, m) for l in lineas for a, m, _ in b.RE_FECHA.findall(l))
    total = sum(meses.values())
    con.execute("UPDATE registros SET factura=?, n_usuarios=?, n_servicios=?, meses_rips=? WHERE clave=?",
                (fac, len(sec.get("USUARIOS", [])), sum(len(v) for k, v in sec.items() if k not in ("USUARIOS", "FACTURAS")),
                 sum(1 for v in meses.values() if v >= 0.1 * total), clave))
    n += 1
con.commit()
print("radicaciones completadas:", n)
