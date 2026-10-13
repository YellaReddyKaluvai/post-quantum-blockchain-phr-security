import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const protectedPrefixes = ["/dashboard"];

const rolePathMap: Record<string, string> = {
  "administrator": "admin",
  "lab technician": "lab-technician",
  "patient": "patient",
  "doctor": "doctor",
  "nurse": "nurse",
};

const knownDashboardSegments = new Set(Object.values(rolePathMap));

function readCookie(request: NextRequest, name: string) {
  return request.cookies.get(name)?.value ?? null;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!protectedPrefixes.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  // Navigation only: the real session is the backend's HttpOnly cookie, which
  // may live on the API's host rather than this one, and every API call is
  // authorised there. These cookies just avoid rendering a dashboard shell to
  // someone who never signed in.
  const session = readCookie(request, "quantumcare_session") ?? readCookie(request, "quantumcare_token");
  const role = readCookie(request, "quantumcare_role");

  if (!session || !role) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const requestedSegment = pathname.split("/")[2];

  if (requestedSegment) {
    const decodedRole = decodeURIComponent(role).toLowerCase();
    const expectedSegment = rolePathMap[decodedRole];

    if (expectedSegment && requestedSegment !== expectedSegment && knownDashboardSegments.has(requestedSegment)) {
      return NextResponse.redirect(new URL(`/dashboard/${expectedSegment}`, request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
