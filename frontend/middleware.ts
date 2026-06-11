import { NextResponse, type NextRequest } from "next/server";
import {
  LANGUAGE_COOKIE,
  LOCALE_HEADER,
  localeFromGeoHeaders,
  normalizeLocale
} from "./lib/i18n";

type RequestWithGeo = NextRequest & {
  geo?: {
    country?: string;
  };
};

export function middleware(request: NextRequest) {
  const cookieLocale = normalizeLocale(request.cookies.get(LANGUAGE_COOKIE)?.value);
  const detectedLocale =
    cookieLocale ??
    localeFromGeoHeaders(
      (headerName) => request.headers.get(headerName),
      (request as RequestWithGeo).geo?.country
    );
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(LOCALE_HEADER, detectedLocale);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders
    }
  });

  if (!cookieLocale) {
    response.cookies.set(LANGUAGE_COOKIE, detectedLocale, {
      maxAge: 60 * 60 * 24 * 365,
      path: "/",
      sameSite: "lax"
    });
  }

  return response;
}

export const config = {
  matcher: "/"
};
