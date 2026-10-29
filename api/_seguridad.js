// Registro de seguridad: cada intento sospechoso se anota en el servidor (worker), que bloquea
// usuarios/IP con muchos fallos y avisa por correo. Si el servidor no responde, la app sigue funcionando.
import { worker } from './_auth.js';

export const ipDe = (req) =>
  String(req.headers['x-forwarded-for'] || req.headers['x-real-ip'] || '').split(',')[0].trim();

export async function evento(req, tipo, extra = {}) {
  try {
    const r = await worker('/seguridad/evento', {
      method: 'POST', signal: AbortSignal.timeout(4000),
      body: JSON.stringify({
        tipo, ip: ipDe(req), ruta: String(req.url || '').split('?')[0].slice(0, 200),
        agente: String(req.headers['user-agent'] || '').slice(0, 300), ...extra,
      }),
    });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

// ¿Usuario o IP bloqueados por intentos fallidos? Si no hay respuesta, no bloquea.
export async function bloqueo(req, usuario) {
  try {
    const qs = new URLSearchParams({ ip: ipDe(req), usuario: usuario || '' });
    const r = await worker('/seguridad/estado?' + qs, { signal: AbortSignal.timeout(4000) });
    return r.ok ? await r.json() : { bloqueado: false };
  } catch { return { bloqueado: false }; }
}
