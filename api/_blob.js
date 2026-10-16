// Lectura de Vercel Blob tolerante a fallos pasajeros (500 / red):
// reintenta con espera y, si Blob sigue fallando, entrega la última copia buena que tenga esta instancia.
import { get } from '@vercel/blob';

const copia = new Map();   // ruta → { texto, t }
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

// Devuelve el texto del blob, o null si no existe. Lanza error solo si falla y no hay copia previa.
export async function leerBlob(ruta, { intentos = 4 } = {}) {
  let ultimo;
  for (let i = 0; i < intentos; i++) {
    try {
      const r = await get(ruta, { access: 'private', useCache: false });
      if (!r || r.statusCode !== 200) return null;
      const texto = await new Response(r.stream).text();
      copia.set(ruta, { texto, t: Date.now() });
      return texto;
    } catch (e) {
      if (e?.name === 'BlobNotFoundError') return null;
      ultimo = e;
      if (i < intentos - 1) await espera(300 * 2 ** i);   // 0,3 s · 0,6 s · 1,2 s
    }
  }
  const c = copia.get(ruta);
  if (c) return c.texto;
  throw ultimo;
}
