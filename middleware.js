// Toda la app exige una sesión válida (cookie firmada). Sin sesión:
//  - páginas → redirige a /login
//  - /api/*  → 401 JSON
// Quedan libres: /login, /api/login, /api/logout y /api/subir (el bot usa su propio token).
import { next } from '@vercel/functions';
import { verificar, leerCookie } from './api/_sesion.js';

export const config = { matcher: ['/((?!login|api/login|api/logout|api/cuenta|api/subir|favicon).*)'] };
// Nota: /api/cuenta?accion=login|logout se llega por las rutas de arriba (rewrites en vercel.json);
// las acciones sesion y clave validan la sesión dentro de la función.

export default async function middleware(request) {
  if (await verificar(leerCookie(request.headers.get('cookie')))) return next();
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/')) {
    return new Response(JSON.stringify({ error: 'Sesión vencida. Vuelve a ingresar.' }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    });
  }
  const destino = new URL('/login', url);
  if (url.pathname !== '/') destino.searchParams.set('next', url.pathname);
  return Response.redirect(destino, 302);
}
