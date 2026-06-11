import type { Metadata } from "next";
import "./globals.css";
import { localeToHtmlLang } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/request-locale";

export const metadata: Metadata = {
  title: "Epix",
  description: "Air Waybills data aggregation PoC",
  icons: {
    icon: "/web.ico",
    shortcut: "/web.ico"
  }
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  const locale = getRequestLocale();

  return (
    <html lang={localeToHtmlLang(locale)}>
      <body>{children}</body>
    </html>
  );
}
