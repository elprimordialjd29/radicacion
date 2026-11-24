# Servidor (worker)

Las consultas al SIE necesitan un navegador real (Playwright), y Vercel no puede ejecutarlo.
Corren en el VPS (Contabo, Ubuntu) como servicio. El VPS también guarda los datos del tablero,
los usuarios y los soportes RIPS.

```
Usuarios ─► radicacion.vercel.app ─► api/*.js (Vercel, con WORKER_TOKEN)
                                         │  https://evaluador3280.duckdns.org:8443
                                         ▼
                              VPS: nginx :8443 ─► radicacion-worker (127.0.0.1:8092)
                                         │  cola: una consulta a la vez, reintentos automáticos
                                         ▼
                              bot/sie_bot.py --oculto ─► SIE Dusakawi
                                         │
                                         ▼
                              bot/descargas/dashboard.json ─► /datos ─► tablero
```

| Elemento | Ubicación |
|---|---|
| Código | `/opt/radicacion` (git clone de `elprimordialjd29/radicacion`) |
| Configuración y secretos | `/opt/radicacion/bot/.env` (permisos 600, no versionado) |
| Historial, Excel y soportes RIPS | `bot/historial.db`, `bot/descargas/`, `bot/descargas/soportes/` |
| Datos del tablero | `bot/descargas/dashboard.json` (lo escribe el bot en cada corrida) |
| Usuarios del tablero | `bot/worker_datos/usuarios.json` (claves con scrypt, permisos 600) |
| Cola de consultas | `bot/worker_datos/consultas.db` |
| Seguridad | `bot/worker_datos/seguridad.db` (eventos 90 días, IP conocidas, avisos enviados) |
| Servicio | `systemctl status radicacion-worker` · logs `journalctl -u radicacion-worker -f` |
| nginx | `/etc/nginx/sites-available/radicacion` (puerto 8443, cert de evaluador3280) |

En el mismo VPS están evaluador3280 y pocketbase: **no se modifican**. La zona horaria del VPS
(Europe/Berlin) no se cambia; el worker corre con `TZ=America/Bogota`.

## Variables en `bot/.env`
| Variable | Uso |
|---|---|
| `SIE_USUARIO`, `SIE_CLAVE` | Ingreso al SIE (la clave la guarda el administrador, ver abajo) |
| `WORKER_TOKEN` | Token que usa Vercel para llamar al worker |
| `SIE_DASHBOARD_URL`, `SIE_DASHBOARD_TOKEN` | Aviso del bot a `/api/subir` (opcional) |
| `ALERTA_SMTP_HOST`, `ALERTA_SMTP_PUERTO`, `ALERTA_SMTP_USUARIO`, `ALERTA_SMTP_CLAVE`, `ALERTA_PARA` | Correo de alertas |

### Cambiar la clave del SIE
Desde una terminal normal del Mac (la clave no se ve ni queda en el historial):
```bash
read -rs "C?Clave SIE: " && printf %s "$C" | ssh root@207.180.243.127 /opt/radicacion/deploy/guardar_clave.py; unset C
```

### Configurar el correo de alertas
```bash
ssh -t root@207.180.243.127 python3 /opt/radicacion/deploy/configurar_alertas.py
```
Con Gmail se usa una **contraseña de aplicación** (requiere verificación en dos pasos). Envía un
correo de prueba y solo guarda si llegó.

## Endpoints del worker (todos con header `x-token`)
| Ruta | Uso |
|---|---|
| `GET /salud` | Estado y consulta en curso |
| `GET/POST /consultas`, `GET /consultas/{id}`, `POST /consultas/{id}/cancelar`, `GET /consultas/{id}/excel` | Cola de consultas |
| `GET /rips` | Soportes RIPS (TXT/JSON, por cápita, por atención o unificado con `meses=`) |
| `GET /datos` | `dashboard.json` |
| `GET/PUT /usuarios` | Usuarios del tablero |
| `GET /monitor` | Memoria, disco, CPU, servicios, cola, almacenamiento y seguridad |
| `GET /duplicados`, `GET /duplicados/excel` | Análisis de facturas duplicadas |
| `GET /frecuencia`, `GET /frecuencia/catalogo`, `PUT /frecuencia/catalogo/{tipo}` | Frecuencia de uso (catálogo en `worker_datos/frecuencia_catalogo.json`). Si falta calcular responde `{calculando, hechos, total}` y lo calcula aparte (`worker/frecuencia_job.py` con los motores de `worker/motores.py`); cachés en `worker_datos/frecuencia_cache/` (`r_*` por RIPS, `c_*` por contrato) |
| `POST /seguridad/evento`, `GET /seguridad/estado`, `GET /seguridad`, `POST /seguridad/prueba` | Registro, bloqueos y alertas |

Toda respuesta 401 del worker se registra como intento externo (`token_invalido_servidor`).

## Frecuencia de uso
Motores en `worker/motores.py` con copias de las tablas de las otras apps en `worker/config/`
(`res3280_cups.json` del evaluador 3280 y `asistencial_cups.json` de la Evaluación Asistencial: si allá
cambian, copiar de nuevo). Se precalcula al arrancar el worker y al terminar cada consulta.

## Consultas programadas y reintentos
- `radicacion-programada.timer` lanza una consulta completa (todos los contratos, RS y RC,
  enero → mes actual) a las **12:00 m y 12:00 a. m. hora Colombia**, como usuario `programada`.
- Si una consulta falla, el worker crea un **reintento** en cola (5, 10, 20, 30 min y luego cada
  hora; máximo 10 intentos; si el error es de inicio de sesión espera mínimo 30 min). Se omite si
  otra consulta igual ya terminó bien. Lanzar una consulta igual adelanta el reintento.
- Correo de aviso si el SIE no deja iniciar sesión (primer fallo) o si se agotan los intentos.

```bash
systemctl list-timers radicacion-programada.timer   # próxima ejecución
systemctl start radicacion-programada.service       # lanzarla ya
```

## Actualizar el servidor
```bash
ssh root@207.180.243.127 /opt/radicacion/deploy/actualizar.sh            # espera a que termine la consulta en curso
ssh root@207.180.243.127 /opt/radicacion/deploy/actualizar.sh --forzar   # reinicia sin esperar
```

## Diagnóstico rápido
- Tablero con «<html>» o 502: `journalctl -u radicacion-worker -n 100` y
  `ls /proc/$(pgrep -f "uvicorn app:app")/fd | wc -l` (fuga de archivos).
- Fallo de login en el SIE: captura en `bot/logs/AAAAMMDD_HHMMSS_login_fallido.png`.
