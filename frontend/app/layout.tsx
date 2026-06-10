import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Omniship Air Waybills",
  description: "Air Waybills data aggregation PoC",
  icons: {
    icon: "/web.ico",
    shortcut: "/web.ico"
  }
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
