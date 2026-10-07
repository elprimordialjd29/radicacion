
// Llama al worker del servidor con el token secreto.
export async function worker(ruta, opciones = {}) {
  const base = (process.env.WORKER_URL || '').replace(/\/$/, '');
  if (!base || !process.env.WORKER_TOKEN) throw new Error('Falta WORKER_URL / WORKER_TOKEN en Vercel');
  return fetch(base + ruta, {
    ...opciones,
    headers: { 'x-token': process.env.WORKER_TOKEN, 'Content-Type': 'application/json', ...(opciones.headers || {}) },
    signal: opciones.signal || AbortSignal.timeout(20000),
  });
}
