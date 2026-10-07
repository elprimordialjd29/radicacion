// Endpoint para el evaluador de cápita asistencial.
// Sirve datos.json con autenticación por token (sin sesión) y cabeceras CORS.
import { get } from '@vercel/blob';

const TOKEN = process.env.EVALUAR_TOKEN || 'DUSAKAWI-RIPS-2026';
const ORIGIN = 'https://evaluacion-rips-2026.vercel.app';

function cors(req, res) {
  const origin = req.headers.origin || '';
  if (origin === ORIGIN || origin.endsWith('.vercel.app') || origin.includes('localhost')) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'x-token, Content-Type');
}

export default async function handler(req, res) {
  cors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Solo GET' });

  const tok = req.headers['x-token'] || req.query.token || '';
  if (tok !== TOKEN) return res.status(401).json({ error: 'Token inválido' });

  try {
    const r = await get('radicacion/datos.json', { access: 'private', useCache: false });
    if (!r || r.statusCode !== 200) return res.status(404).json({ error: 'Sin datos todavía' });
    const texto = await new Response(r.stream).text();
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.status(200).send(texto);
  } catch (e) {
    if (e && e.name === 'BlobNotFoundError') return res.status(404).json({ error: 'Sin datos todavía' });
    return res.status(500).json({ error: String(e?.message || e) });
  }
}
