// Protege todo el dashboard con usuario/clave (Basic Auth).
// /api/subir queda fuera: el bot se autentica con su propio token (x-token).
import { next } from '@vercel/functions';

export const config = { matcher: ['/((?!api/subir).*)'] };

export default function middleware(request) {
  const clave = process.env.DASHBOARD_CLAVE;
  if (!clave) {
    return new Response('Falta configurar DASHBOARD_CLAVE en Vercel', { status: 503 });
  }
  const auth = request.headers.get('authorization') || '';
  if (auth.startsWith('Basic ')) {
    const [, pass] = atob(auth.slice(6)).split(/:(.*)/s);
    if (pass === clave) return next();
  }
  return new Response('Acceso restringido', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Radicacion Capita", charset="UTF-8"' },
  });
}
