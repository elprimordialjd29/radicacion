"""Registro de seguridad del tablero de radicación.

- Guarda cada intento sospechoso (clave errada, token inválido, permiso negado…) en la tabla `eventos`.
- Bloquea temporalmente un usuario o una IP con muchos intentos fallidos de ingreso.
- Avisa por correo (SMTP) sin inundar: un correo por tipo de evento e IP cada 30 minutos.

Configuración del correo en bot/.env (la escribe deploy/configurar_alertas.py):
  ALERTA_SMTP_HOST, ALERTA_SMTP_PUERTO, ALERTA_SMTP_USUARIO, ALERTA_SMTP_CLAVE, ALERTA_PARA
"""
import os
import smtplib
import sqlite3
import ssl
import threading
import time
from contextlib import closing
from datetime import datetime
from email.message import EmailMessage

VENTANA = 15 * 60          # segundos en que se cuentan los intentos fallidos
MAX_USUARIO = 5            # fallos seguidos de un mismo usuario → bloqueo
MAX_IP = 10                # fallos desde una misma IP → bloqueo
AVISO_IP = 3               # a partir de cuántos fallos de una IP se avisa por correo
SILENCIO = 30 * 60         # no repetir el mismo aviso (tipo + IP) antes de esto

TITULOS = {
    "login_fallido": "Intentos de ingreso con clave o usuario errado",
    "bloqueo": "Usuario o IP bloqueados por intentos fallidos",
    "token_invalido": "Acceso a la API con token inválido",
    "token_invalido_servidor": "Acceso directo al servidor con token inválido",
    "permiso_denegado": "Usuario intentó entrar a algo sin permiso",
    "admin_ip_nueva": "Ingreso de un administrador desde una IP nueva",
}
NIVEL = {"login_fallido": 1, "permiso_denegado": 1, "admin_ip_nueva": 1,
         "token_invalido": 2, "token_invalido_servidor": 2, "bloqueo": 3}


class Seguridad:
    def __init__(self, ruta_db):
        self.ruta = str(ruta_db)
        self._lock = threading.Lock()
        with closing(self._con()) as con, con:
            con.execute("""CREATE TABLE IF NOT EXISTS eventos(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, fecha TEXT, tipo TEXT, nivel INTEGER,
                ip TEXT, usuario TEXT, ruta TEXT, detalle TEXT, agente TEXT)""")
            con.execute("CREATE INDEX IF NOT EXISTS ev_ts ON eventos(ts)")
            con.execute("""CREATE TABLE IF NOT EXISTS avisos(clave TEXT PRIMARY KEY, ts REAL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS ips_conocidas(usuario TEXT, ip TEXT, ts REAL,
                PRIMARY KEY(usuario, ip))""")

    def _con(self):
        con = sqlite3.connect(self.ruta, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------------------ bloqueos
    def _fallos(self, con, campo, valor):
        return con.execute(f"SELECT COUNT(*) FROM eventos WHERE tipo='login_fallido' AND {campo}=? AND ts>?",
                           (valor, time.time() - VENTANA)).fetchone()[0]

    def estado(self, ip="", usuario=""):
        """¿Está bloqueado este usuario o esta IP? Devuelve (bloqueado, minutos_restantes)."""
        with closing(self._con()) as con:
            for campo, valor, maximo in (("usuario", usuario, MAX_USUARIO), ("ip", ip, MAX_IP)):
                if not valor:
                    continue
                filas = con.execute(
                    f"SELECT ts FROM eventos WHERE tipo='login_fallido' AND {campo}=? AND ts>? ORDER BY ts DESC",
                    (valor, time.time() - VENTANA)).fetchall()
                if len(filas) >= maximo:
                    # se libera cuando el fallo n.º `maximo` (contando desde el más reciente) sale de la ventana
                    libre = filas[maximo - 1]["ts"] + VENTANA
                    return True, max(1, round((libre - time.time()) / 60))
        return False, 0

    # ----------------------------------------------------------------- registrar
    def registrar(self, tipo, ip="", usuario="", ruta="", detalle="", agente=""):
        ahora = time.time()
        fecha = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._lock, closing(self._con()) as con, con:
            con.execute("INSERT INTO eventos(ts, fecha, tipo, nivel, ip, usuario, ruta, detalle, agente) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (ahora, fecha, tipo, NIVEL.get(tipo, 1), ip, usuario, ruta, detalle[:500], agente[:300]))
            # se guardan 90 días
            con.execute("DELETE FROM eventos WHERE ts<?", (ahora - 90 * 86400,))
        bloqueado, minutos = self.estado(ip, usuario) if tipo == "login_fallido" else (False, 0)
        self._quizas_avisar(tipo, ip, usuario, ruta, detalle, agente, bloqueado, minutos)
        return {"bloqueado": bloqueado, "minutos": minutos}

    def ingreso_ok(self, ip, usuario, es_admin):
        """Recuerda las IP de cada usuario; si un admin entra desde una IP nunca vista, avisa."""
        with self._lock, closing(self._con()) as con, con:
            nueva = not con.execute("SELECT 1 FROM ips_conocidas WHERE usuario=? AND ip=?", (usuario, ip)).fetchone()
            primera = not con.execute("SELECT 1 FROM ips_conocidas WHERE usuario=?", (usuario,)).fetchone()
            con.execute("INSERT OR REPLACE INTO ips_conocidas(usuario, ip, ts) VALUES (?,?,?)", (usuario, ip, time.time()))
        # la primera IP de cada usuario se aprende sin avisar
        if es_admin and nueva and not primera and ip:
            self.registrar("admin_ip_nueva", ip=ip, usuario=usuario, detalle="Ingreso correcto desde una IP nueva")

    # -------------------------------------------------------------------- avisos
    def _quizas_avisar(self, tipo, ip, usuario, ruta, detalle, agente, bloqueado, minutos):
        if tipo == "login_fallido":
            with closing(self._con()) as con:
                n_ip = self._fallos(con, "ip", ip) if ip else 0
            if bloqueado:
                tipo = "bloqueo"
                detalle = f"{detalle} · bloqueado {minutos} min"
            elif n_ip < AVISO_IP:
                return
            detalle = f"{detalle} · {n_ip} intento(s) fallidos desde esta IP en 15 min"
        clave = f"{tipo}|{ip or usuario}"
        with self._lock, closing(self._con()) as con, con:
            fila = con.execute("SELECT ts FROM avisos WHERE clave=?", (clave,)).fetchone()
            if fila and time.time() - fila["ts"] < SILENCIO:
                return
            con.execute("INSERT OR REPLACE INTO avisos(clave, ts) VALUES (?,?)", (clave, time.time()))
        cuerpo = (f"{TITULOS.get(tipo, tipo)}\n\n"
                  f"Fecha:   {datetime.now().astimezone().strftime('%d/%m/%Y %I:%M %p')} (hora del servidor)\n"
                  f"IP:      {ip or '—'}\n"
                  f"Usuario: {usuario or '—'}\n"
                  f"Ruta:    {ruta or '—'}\n"
                  f"Detalle: {detalle or '—'}\n"
                  f"Navegador / cliente: {agente or '—'}\n\n"
                  "Puedes ver todos los intentos en radicacion.vercel.app → Servidor → Seguridad.\n"
                  "No se repetirá este mismo aviso para esta IP en los próximos 30 minutos.")
        threading.Thread(target=enviar_correo, args=(f"⚠ Radicación cápita: {TITULOS.get(tipo, tipo)}", cuerpo),
                         daemon=True).start()

    # ------------------------------------------------------------------- consulta
    def listar(self, limite=100):
        with closing(self._con()) as con:
            filas = [dict(r) for r in con.execute(
                "SELECT fecha, tipo, nivel, ip, usuario, ruta, detalle, agente FROM eventos ORDER BY ts DESC LIMIT ?",
                (limite,))]
            dia = con.execute("SELECT COUNT(*) FROM eventos WHERE ts>?", (time.time() - 86400,)).fetchone()[0]
            semana = con.execute("SELECT COUNT(*) FROM eventos WHERE ts>?", (time.time() - 7 * 86400,)).fetchone()[0]
            ips = con.execute("SELECT COUNT(DISTINCT ip) FROM eventos WHERE ts>?", (time.time() - 7 * 86400,)).fetchone()[0]
        return {"eventos": filas, "ultimas_24h": dia, "ultimos_7d": semana, "ips_7d": ips,
                "correo_configurado": correo_configurado(), "titulos": TITULOS}


def correo_configurado():
    return all(os.getenv(k) for k in ("ALERTA_SMTP_USUARIO", "ALERTA_SMTP_CLAVE", "ALERTA_PARA"))


def enviar_correo(asunto, cuerpo):
    """Envía el aviso. Devuelve (ok, mensaje). Sin configuración, no hace nada."""
    if not correo_configurado():
        return False, "Correo de alertas sin configurar"
    host = os.getenv("ALERTA_SMTP_HOST", "smtp.gmail.com")
    puerto = int(os.getenv("ALERTA_SMTP_PUERTO", "465"))
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = os.getenv("ALERTA_SMTP_USUARIO")
    msg["To"] = os.getenv("ALERTA_PARA")
    msg.set_content(cuerpo)
    try:
        if puerto == 465:
            with smtplib.SMTP_SSL(host, puerto, context=ssl.create_default_context(), timeout=20) as s:
                s.login(os.getenv("ALERTA_SMTP_USUARIO"), os.getenv("ALERTA_SMTP_CLAVE"))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, puerto, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(os.getenv("ALERTA_SMTP_USUARIO"), os.getenv("ALERTA_SMTP_CLAVE"))
                s.send_message(msg)
        return True, "enviado"
    except Exception as e:   # un fallo del correo nunca debe tumbar el worker
        print(f"[seguridad] no se pudo enviar el correo: {e}", flush=True)
        return False, str(e)
