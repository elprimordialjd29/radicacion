# Servidor de consultas (worker)

Las consultas al SIE necesitan un navegador real (Playwright), y Vercel no puede
ejecutarlo. Por eso corren en el VPS (Contabo, Ubuntu) como servicio.

```
Usuarios ─► radicacion.vercel.app ─► /api/consultas (Vercel, con WORKER_TOKEN)
                                         │
                                         ▼  https://evaluador3280.duckdns.org:8443
                              VPS: nginx :8443 ─► radicacion-worker (127.0.0.1:8092)
                                         │  cola, una consulta a la vez
                                         ▼
                              bot/sie_bot.py --oculto ─► SIE Dusakawi
                                         │
                                         ▼  POST /api/subir (SUBIR_TOKEN)
                              Vercel Blob privado ─► dashboard actualizado
```

| Elemento | Ubicación |
|---|---|
| Código | `/opt/radicacion` (git clone del repo) |
| Configuración y secretos | `/opt/radicacion/bot/.env` (permisos 600, no versionado) |
| Historial, Excel y soportes | `/opt/radicacion/bot/historial.db`, `bot/descargas/` |
| Cola de consultas | `/opt/radicacion/bot/worker_datos/consultas.db` |
| Servicio | `systemctl status radicacion-worker` |
| Logs | `journalctl -u radicacion-worker -f` |
| nginx | `/etc/nginx/sites-available/radicacion` (puerto 8443) |

## Variables en `bot/.env` del servidor
`SIE_USUARIO`, `SIE_CLAVE`, `SIE_DASHBOARD_URL`, `SIE_DASHBOARD_TOKEN`, `WORKER_TOKEN`.

## Variables en Vercel
`WORKER_URL=https://evaluador3280.duckdns.org:8443` y `WORKER_TOKEN` (el mismo del servidor).

## Consultas programadas
`radicacion-programada.timer` lanza una consulta completa (todos los contratos, RS y RC,
enero → mes actual) a las **12:00 m y 12:00 a. m. hora Colombia**. Entra a la cola del worker
como usuario `programada`.
```bash
systemctl list-timers radicacion-programada.timer   # próxima ejecución
systemctl start radicacion-programada.service       # lanzarla ya
```

## Actualizar el servidor
```bash
ssh root@207.180.243.127 /opt/radicacion/deploy/actualizar.sh
```

## Usuarios del dashboard
En Vercel, `DASHBOARD_USUARIOS="ana:clave1,luis:clave2"` crea usuarios con nombre.
Cada consulta queda registrada con quien la lanzó. `DASHBOARD_CLAVE` sigue
funcionando como clave compartida.
