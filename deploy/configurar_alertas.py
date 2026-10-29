#!/usr/bin/env python3
"""Configura el correo de alertas de seguridad (lo ejecuta el administrador en el servidor).

    python3 /opt/radicacion/deploy/configurar_alertas.py

Con Gmail: activa la verificación en dos pasos y crea una "contraseña de aplicación"
(myaccount.google.com → Seguridad → Contraseñas de aplicaciones). Esa contraseña de 16 letras
es la que se escribe aquí, no la clave normal del correo. Queda guardada solo en bot/.env (permisos 600).
"""
import getpass
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / "bot" / ".env"


def escribir(valores):
    lineas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    lineas = [l for l in lineas if l.split("=", 1)[0] not in valores]
    lineas += [f"{k}={v}" for k, v in valores.items()]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.chmod(ENV, 0o600)


def main():
    print("Correo de alertas de seguridad — radicación cápita\n")
    host = input("Servidor SMTP [smtp.gmail.com]: ").strip() or "smtp.gmail.com"
    puerto = input("Puerto [465]: ").strip() or "465"
    usuario = input("Correo que ENVÍA las alertas (ej. tucorreo@gmail.com): ").strip()
    clave = getpass.getpass("Contraseña de aplicación de ese correo (no se muestra): ").strip().replace(" ", "")
    para = input(f"Correo que RECIBE las alertas [{usuario}]: ").strip() or usuario
    if not (usuario and clave and para):
        sys.exit("Faltan datos; no se guardó nada.")
    valores = {"ALERTA_SMTP_HOST": host, "ALERTA_SMTP_PUERTO": puerto, "ALERTA_SMTP_USUARIO": usuario,
               "ALERTA_SMTP_CLAVE": clave, "ALERTA_PARA": para}
    os.environ.update(valores)
    sys.path.insert(0, str(RAIZ / "worker"))
    from seguridad import enviar_correo
    ok, msg = enviar_correo("✅ Radicación cápita: prueba de alertas",
                            "Las alertas de seguridad del tablero llegarán a este correo.")
    if not ok:
        sys.exit(f"No se pudo enviar el correo de prueba ({msg}). No se guardó nada; revisa los datos.")
    escribir(valores)
    subprocess.run(["systemctl", "restart", "radicacion-worker"], check=False)
    print(f"\n✔ Correo de prueba enviado a {para}. Configuración guardada y worker reiniciado.")


if __name__ == "__main__":
    main()
