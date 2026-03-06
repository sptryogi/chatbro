import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  
  // Daftar path yang boleh diakses tanpa login
  const publicPaths = ['/login', '/register', '/api/auth'];
  const isPublicPath = publicPaths.some(publicPath => 
    path === publicPath || path.startsWith(publicPath + '/')
  );
  
  // Static files dan assets
  const isStaticFile = 
    path.startsWith('/_next') || 
    path.startsWith('/static') ||
    path.startsWith('/favicon') ||
    path.includes('.');
  
  // Kalau public path atau static file, lanjutkan
  if (isPublicPath || isStaticFile) {
    return NextResponse.next();
  }
  
  // Cek token di cookies atau localStorage (via cookie)
  const token = request.cookies.get('chatbro_token')?.value;
  
  // Kalau tidak ada token, redirect ke login
  if (!token) {
    const loginUrl = new URL('/login', request.url);
    // Simpan URL yang dituju supaya bisa redirect balik setelah login
    loginUrl.searchParams.set('callbackUrl', path);
    return NextResponse.redirect(loginUrl);
  }
  
  // Kalau sudah login dan akses /login, redirect ke home
  if (path === '/login' && token) {
    return NextResponse.redirect(new URL('/', request.url));
  }
  
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
