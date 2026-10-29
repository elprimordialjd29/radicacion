// Antes guardaba en Vercel Blob el JSON que publica el bot. Ahora el bot deja ese JSON en el servidor
// (bot/descargas/dashboard.json) y el tablero lo lee de allí: este endpoint solo confirma, para no romper al bot.
import { evento } from './_seguridad.js';

export const config = { api: { bodyParser: { sizeLimit: '4mb' } } };

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  const token = process.env.SUBIR_TOKEN;
  if (!token || req.headers['x-token'] !== token) {
    await evento(req, 'token_invalido', { detalle: 'publicación del bot con token errado' });
    return res.status(401).json({ error: 'Token inválido' });
  }
  const datos = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  return res.status(200).json({ ok: true, origen: 'servidor', contratos: datos?.contratos?.length || 0 });
}
