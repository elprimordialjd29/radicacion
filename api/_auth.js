// Usuario que hizo la petición (viene del Basic Auth que ya validó middleware.js).
export function usuarioDe(req) {
  const h = req.headers.authorization || '';
  if (!h.startsWith('Basic ')) return 'desconocido';
  const [u] = Buffer.from(h.slice(6), 'base64').toString('utf8').split(':');
  return (u || 'desconocido').trim().slice(0, 60);
}

// Llama al worker del servidor con el token secreto.
export async function worker(ruta, opciones = {}) {
  const base = (process.env.WORKER_URL || '').replace(/\/$/, '');
  if (!base || !process.env.WORKER_TOKEN) throw new Error('Falta WORKER_URL / WORKER_TOKEN en Vercel');
  return fetch(base + ruta, {
    ...opciones,
    headers: { 'x-token': process.env.WORKER_TOKEN, 'Content-Type': 'application/json', ...(opciones.headers || {}) },
    signal: AbortSignal.timeout(20000),
  });
}
