export const DEFAULT_LOCALE = "en";
export const LANGUAGE_COOKIE = "epix_locale";
export const LOCALE_HEADER = "x-epix-locale";

export type Locale = "en" | "zh";

const CHINESE_LOCALE_REGION_CODES = ["CN", "HK", "TW"];
const GEO_COUNTRY_HEADERS = [
  "x-vercel-ip-country",
  "cf-ipcountry",
  "cloudfront-viewer-country",
  "x-country-code",
  "x-appengine-country"
];

export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) {
    return null;
  }

  const normalizedValue = value.toLowerCase();

  if (normalizedValue === "zh" || normalizedValue.startsWith("zh-")) {
    return "zh";
  }

  if (normalizedValue === "en" || normalizedValue.startsWith("en-")) {
    return "en";
  }

  return null;
}

export function localeFromRegionCode(regionCode: string | null | undefined): Locale {
  const normalizedRegionCode = regionCode?.trim().toUpperCase();

  if (
    normalizedRegionCode &&
    CHINESE_LOCALE_REGION_CODES.includes(normalizedRegionCode)
  ) {
    return "zh";
  }

  return DEFAULT_LOCALE;
}

export function getRegionCodeFromHeaders(
  readHeader: (name: string) => string | null | undefined,
  geoCountry?: string | null
): string | null {
  if (geoCountry) {
    return geoCountry;
  }

  for (const headerName of GEO_COUNTRY_HEADERS) {
    const headerValue = readHeader(headerName);

    if (headerValue) {
      return headerValue;
    }
  }

  return null;
}

export function localeFromGeoHeaders(
  readHeader: (name: string) => string | null | undefined,
  geoCountry?: string | null
): Locale {
  return localeFromRegionCode(getRegionCodeFromHeaders(readHeader, geoCountry));
}

export function localeToHtmlLang(locale: Locale): string {
  return locale === "zh" ? "zh-CN" : "en";
}
