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

  const accessToken = readCookie(request, "quantumcare_token");
  const role = readCookie(request, "quantumcare_role");

  if (!accessToken || !role) {
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
