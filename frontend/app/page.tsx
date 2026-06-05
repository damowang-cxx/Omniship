"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Globe2,
  Mail,
  MapPin,
  Plane,
  ShieldCheck,
  ShipWheel,
  Warehouse
} from "lucide-react";
import { getCurrentUser } from "@/lib/api";
import styles from "./page.module.css";

const services = [
  {
    icon: Plane,
    title: "Priority air freight",
    copy: "Time-sensitive air cargo coordination for cross-border shipments, with clear milestone visibility from pre-alert to arrival."
  },
  {
    icon: ShieldCheck,
    title: "Customs-ready documentation",
    copy: "Structured shipment checks help customers prepare accurate air waybill and pre-alert documents before handover."
  },
  {
    icon: Warehouse,
    title: "Arrival coordination",
    copy: "Operational follow-up across airline, ground handling, warehouse receipt and release milestones."
  }
];

const processSteps = [
  "Share shipment data and documents",
  "Validate pre-alert information",
  "Coordinate airline and arrival milestones",
  "Monitor release and outbound progress"
];

export default function LandingPage() {
  const router = useRouter();

  useEffect(() => {
    async function redirectIfLoggedIn() {
      try {
        await getCurrentUser();
        router.replace("/waybill-uploads");
      } catch {
        // Public visitors stay on the EPIX landing page.
      }
    }

    void redirectIfLoggedIn();
  }, [router]);

  return (
    <main className={styles.page}>
      <header className={styles.navbar}>
        <Link className={styles.brand} href="/" aria-label="EPIX home">
          <span className={styles.brandMark}>E</span>
          <span>EPIX</span>
        </Link>
        <nav className={styles.navLinks} aria-label="Landing navigation">
          <a href="#services">Services</a>
          <a href="#process">Process</a>
          <a href="#contact">Contact</a>
        </nav>
        <Link className={styles.loginButton} href="/login">
          Login
        </Link>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroOverlay} />
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>Air freight logistics for cross-border teams</p>
          <h1>EPIX keeps urgent air cargo moving with clarity.</h1>
          <p className={styles.heroCopy}>
            We coordinate air waybill preparation, pre-alert documentation and arrival
            follow-up so partners can move shipments through complex international
            handovers with fewer blind spots.
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryCta} href="#services">
              Explore services
              <ArrowRight aria-hidden="true" size={18} />
            </a>
            <a className={styles.secondaryCta} href="#contact">
              Contact EPIX
            </a>
          </div>
        </div>
      </section>

      <section className={styles.metrics} aria-label="EPIX operating strengths">
        <div>
          <Clock3 aria-hidden="true" size={22} />
          <strong>Time-critical</strong>
          <span>Built for air freight windows and arrival milestones.</span>
        </div>
        <div>
          <Globe2 aria-hidden="true" size={22} />
          <strong>Cross-border</strong>
          <span>Designed for international partners and destination handovers.</span>
        </div>
        <div>
          <CheckCircle2 aria-hidden="true" size={22} />
          <strong>Document-aware</strong>
          <span>Shipment data, pre-alert files and AWB details handled together.</span>
        </div>
      </section>

      <section className={styles.section} id="services">
        <div className={styles.sectionHeader}>
          <p className={styles.eyebrow}>Services</p>
          <h2>Air freight operations with disciplined follow-through.</h2>
          <p>
            EPIX focuses on the details that matter before and after arrival:
            shipment data quality, document readiness, milestone follow-up and partner
            communication.
          </p>
        </div>
        <div className={styles.serviceGrid}>
          {services.map((service) => {
            const Icon = service.icon;
            return (
              <article className={styles.serviceCard} key={service.title}>
                <Icon aria-hidden="true" size={24} />
                <h3>{service.title}</h3>
                <p>{service.copy}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className={styles.processBand} id="process">
        <div className={styles.processText}>
          <p className={styles.eyebrow}>Process</p>
          <h2>From pre-alert to outbound visibility.</h2>
          <p>
            Our workflow is built around practical shipment control: prepare early,
            validate documents, coordinate arrival stakeholders and keep status changes
            visible for the teams who need to act.
          </p>
        </div>
        <ol className={styles.processList}>
          {processSteps.map((step, index) => (
            <li key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.whySection}>
        <div className={styles.sectionHeader}>
          <p className={styles.eyebrow}>Why EPIX</p>
          <h2>A focused partner for air cargo visibility.</h2>
        </div>
        <div className={styles.whyGrid}>
          <div>
            <ShipWheel aria-hidden="true" size={24} />
            <h3>Operational focus</h3>
            <p>Clear communication across shipment preparation, arrival and release.</p>
          </div>
          <div>
            <Plane aria-hidden="true" size={24} />
            <h3>Air-first expertise</h3>
            <p>Processes shaped around the urgency and precision of air freight.</p>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" size={24} />
            <h3>Quality control</h3>
            <p>Document and shipment checks reduce avoidable delays before handover.</p>
          </div>
        </div>
      </section>

      <footer className={styles.contactFooter} id="contact">
        <div>
          <p className={styles.eyebrow}>Contact</p>
          <h2>Talk to EPIX about your next air shipment.</h2>
        </div>
        <div className={styles.contactGrid}>
          <span>
            <Mail aria-hidden="true" size={18} />
            contact@example.com
          </span>
          <span>
            <Plane aria-hidden="true" size={18} />
            +00 000 000 000
          </span>
          <span>
            <MapPin aria-hidden="true" size={18} />
            Global air freight desk
          </span>
        </div>
      </footer>
    </main>
  );
}
