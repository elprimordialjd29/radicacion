// Recibe el JSON que publica el bot (bot/sie_bot.py) y lo guarda en Vercel Blob PRIVADO.
import { put } from '@vercel/blob';

export const config = { api: { bodyParser: { sizeLimit: '4mb' } } };

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  const token = process.env.SUBIR_TOKEN;
  if (!token || req.headers['x-token'] !== token) {
    return res.status(401).json({ error: 'Token inválido' });
  }
  const datos = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  if (!datos || !Array.isArray(datos.contratos)) {
    return res.status(400).json({ error: 'Formato inesperado' });
  }
  await put('radicacion/datos.json', JSON.stringify(datos), {
    access: 'private',
    allowOverwrite: true,
    addRandomSuffix: false,
    contentType: 'application/json',
  });
  return res.status(200).json({ ok: true, contratos: datos.contratos.length,
                                registros: (datos.registros || []).length });
}
