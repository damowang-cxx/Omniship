import { cookies, headers } from "next/headers";
import {
  DEFAULT_LOCALE,
  LANGUAGE_COOKIE,
  LOCALE_HEADER,
  Locale,
  normalizeLocale
} from "./i18n";

export function getRequestLocale(): Locale {
  const requestHeaders = headers();
  const headerLocale = normalizeLocale(requestHeaders.get(LOCALE_HEADER));

  if (headerLocale) {
    return headerLocale;
  }

  const cookieLocale = normalizeLocale(cookies().get(LANGUAGE_COOKIE)?.value);

  return cookieLocale ?? DEFAULT_LOCALE;
}
