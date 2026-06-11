import LandingPageClient from "./LandingPageClient";
import { getRequestLocale } from "@/lib/request-locale";

export default function LandingPage() {
  return <LandingPageClient initialLocale={getRequestLocale()} />;
}
