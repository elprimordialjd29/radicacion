// Datos del tablero y usuarios: se guardan en el servidor (worker), no en Vercel Blob
// (Blob en plan Hobby se suspendió por exceder la cuota de operaciones).
// Lectura tolerante: reintenta y, si el servidor no responde, usa la última copia buena de esta instancia.
import { worker } from './_auth.js';

const copia = new Map();   // ruta → { texto, t }
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

// Devuelve el texto, o null si no existe (404). Lanza error solo si falla y no hay copia previa.
export async function leerServidor(ruta, { intentos = 3, cacheMs = 0 } = {}) {
  const c = copia.get(ruta);
  if (c && cacheMs && Date.now() - c.t < cacheMs) return c.texto;
  let ultimo;
  for (let i = 0; i < intentos; i++) {
    try {
      const r = await worker(ruta);
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`servidor ${r.status}`);
      const texto = await r.text();
      copia.set(ruta, { texto, t: Date.now() });
      return texto;
    } catch (e) {
      ultimo = e;
      if (i < intentos - 1) await espera(400 * 2 ** i);
    }
  }
  if (c) return c.texto;
  throw ultimo;
}

export async function guardarServidor(ruta, texto) {
  const r = await worker(ruta, { method: 'PUT', body: texto });
  if (!r.ok) throw new Error(`No se pudo guardar (${r.status})`);
  copia.set(ruta, { texto, t: Date.now() });
}
