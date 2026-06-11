import { describe, expect, it } from "vitest";
import { localeFromGeoHeaders, localeFromRegionCode, normalizeLocale } from "./i18n";

describe("i18n locale helpers", () => {
  it("normalizes supported locale values", () => {
    expect(normalizeLocale("zh-CN")).toBe("zh");
    expect(normalizeLocale("en-US")).toBe("en");
    expect(normalizeLocale("fr-FR")).toBeNull();
  });

  it("uses Chinese for China, Hong Kong and Taiwan region codes", () => {
    expect(localeFromRegionCode("CN")).toBe("zh");
    expect(localeFromRegionCode("HK")).toBe("zh");
    expect(localeFromRegionCode("TW")).toBe("zh");
  });

  it("uses English outside the configured Chinese regions", () => {
    expect(localeFromRegionCode("US")).toBe("en");
    expect(localeFromRegionCode("NL")).toBe("en");
    expect(localeFromRegionCode(undefined)).toBe("en");
  });

  it("reads common IP country headers", () => {
    expect(
      localeFromGeoHeaders((headerName) =>
        headerName === "cf-ipcountry" ? "HK" : null
      )
    ).toBe("zh");
    expect(localeFromGeoHeaders(() => null, "TW")).toBe("zh");
    expect(
      localeFromGeoHeaders((headerName) =>
        headerName === "x-vercel-ip-country" ? "DE" : null
      )
    ).toBe("en");
  });
});
