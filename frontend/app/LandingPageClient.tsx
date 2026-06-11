"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Globe2,
  Languages,
  Mail,
  MapPin,
  Plane,
  ShieldCheck,
  Warehouse
} from "lucide-react";
import { getCurrentUser } from "@/lib/api";
import {
  LANGUAGE_COOKIE,
  Locale,
  localeToHtmlLang
} from "@/lib/i18n";
import styles from "./page.module.css";

type LandingContent = {
  nav: {
    label: string;
    home: string;
    service: string;
    why: string;
    contact: string;
    login: string;
  };
  language: {
    buttonLabel: string;
    english: string;
    englishShort: string;
    chinese: string;
    chineseShort: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    copy: string;
    primaryCta: string;
    secondaryCta: string;
  };
  metricsLabel: string;
  metrics: Array<{
    icon: typeof Clock3;
    title: string;
    copy: string;
  }>;
  services: {
    eyebrow: string;
    cards: Array<{
      icon: typeof Plane;
      title: string;
      copy: string;
    }>;
  };
  why: {
    eyebrow: string;
    title: string;
    copy: string;
    points: string[];
  };
  contact: {
    eyebrow: string;
    title: string;
    email: string;
    phone: string;
    location: string;
  };
  partners: {
    label: string;
  };
};

const partnerLogos = [
  {
    name: "Colissimo",
    className: styles.colissimoLogo
  },
  {
    name: "FedEx",
    className: styles.fedexLogo
  },
  {
    name: "DHL",
    className: styles.dhlLogo
  },
  {
    name: "DPD",
    className: styles.dpdLogo
  },
  {
    name: "UPS",
    className: styles.upsLogo
  },
  {
    name: "Pedller",
    className: styles.pedllerLogo
  }
];

const landingContent: Record<Locale, LandingContent> = {
  en: {
    nav: {
      label: "Landing navigation",
      home: "HOME",
      service: "SERVICE",
      why: "WHY EPIX",
      contact: "CONTACT",
      login: "Login"
    },
    language: {
      buttonLabel: "Change language",
      english: "English",
      englishShort: "EN",
      chinese: "中文",
      chineseShort: "中"
    },
    hero: {
      eyebrow: "FROM CROSSBORDER TO DOORSTEP.",
      title: "EPIX, Your Trusted Partner for E-commerce Logistics.",
      copy:
        "One-stop e-commerce logistics solutions, specializing in customs clearance, last-mile delivery, and European trucking services.",
      primaryCta: "Explore services",
      secondaryCta: "Contact EPIX"
    },
    metricsLabel: "EPIX operating strengths",
    metrics: [
      {
        icon: Clock3,
        title: "Real-Time Tracking",
        copy:
          "Monitor shipments at every stage with real-time status updates, transportation milestones, and delivery progress, ensuring complete visibility from origin to destination."
      },
      {
        icon: Globe2,
        title: "Centralized Shipment Management",
        copy:
          "Manage transportation, customs clearance, and delivery information through a single platform, simplifying operations and improving efficiency across the supply chain."
      },
      {
        icon: CheckCircle2,
        title: "Data Transparency & Control",
        copy:
          "Access accurate shipment data, automated notifications, and performance insights, enabling faster decision-making and greater operational control."
      }
    ],
    services: {
      eyebrow: "Services",
      cards: [
        {
          icon: Plane,
          title: "Fast Air Freight Solutions",
          copy:
            "Priority air freight services designed to reduce transit times and accelerate supply chain performance."
        },
        {
          icon: ShieldCheck,
          title: "European Customs Expertise",
          copy:
            "Professional customs clearance support across the EU and UK, ensuring smooth and compliant import processes."
        },
        {
          icon: Warehouse,
          title: "Integrated Last-Mile Delivery",
          copy:
            "Direct access to leading carrier networks and local distribution partners for efficient final-mile delivery."
        },
        {
          icon: Globe2,
          title: "Real-Time Shipment Visibility",
          copy:
            "Advanced tracking tools provide end-to-end shipment monitoring and full supply chain transparency."
        },
        {
          icon: CheckCircle2,
          title: "Flexible Logistics Solutions",
          copy:
            "Customized transportation and delivery options tailored to e-commerce, retail, and B2B supply chains."
        },
        {
          icon: Clock3,
          title: "Dedicated Customer Support",
          copy:
            "Responsive logistics specialists offering proactive communication and operational support throughout the shipment journey."
        }
      ]
    },
    why: {
      eyebrow: "Why EPIX",
      title: "Why EPIX",
      copy:
        "Combining global reach with local expertise, EPIX provide seamless e-commerce logistics solutions across Europe, including customs clearance, transportation, and reliable last-mile delivery services.",
      points: [
        "Extensive European Network",
        "End-to-End Logistics Solutions",
        "Reliable Customs Clearance Expertise",
        "Flexible Transportation Options",
        "Trusted Last-Mile Delivery Partners",
        "Dedicated Local Support Team",
        "Fast Response and Operational Excellence",
        "Real-Time Shipment Tracking & Trace."
      ]
    },
    contact: {
      eyebrow: "Contact",
      title: "Talk to EPIX about your next air shipment.",
      email: "hello@epix-logistics.com",
      phone: "+31 684747361",
      location: "Global air freight desk"
    },
    partners: {
      label: "Logistics partners"
    }
  },
  zh: {
    nav: {
      label: "宣传页导航",
      home: "首页",
      service: "服务",
      why: "为什么选择 EPIX",
      contact: "联系",
      login: "登录"
    },
    language: {
      buttonLabel: "切换语言",
      english: "English",
      englishShort: "EN",
      chinese: "中文",
      chineseShort: "中"
    },
    hero: {
      eyebrow: "从跨境到门到门交付。",
      title: "EPIX，您值得信赖的电商物流合作伙伴。",
      copy:
        "一站式电商物流解决方案，专注清关、最后一公里派送与欧洲卡车运输服务。",
      primaryCta: "了解服务",
      secondaryCta: "联系 EPIX"
    },
    metricsLabel: "EPIX 运营优势",
    metrics: [
      {
        icon: Clock3,
        title: "实时追踪",
        copy:
          "通过实时状态更新、运输节点和派送进度，监控货件每一阶段，确保从始发地到目的地全程可见。"
      },
      {
        icon: Globe2,
        title: "集中化货件管理",
        copy:
          "通过单一平台管理运输、清关与派送信息，简化操作并提升供应链效率。"
      },
      {
        icon: CheckCircle2,
        title: "数据透明与管控",
        copy:
          "获取准确货件数据、自动通知和绩效洞察，支持更快决策和更强运营控制。"
      }
    ],
    services: {
      eyebrow: "服务",
      cards: [
        {
          icon: Plane,
          title: "快速空运解决方案",
          copy:
            "优先空运服务旨在缩短运输时间，加速供应链履约表现。"
        },
        {
          icon: ShieldCheck,
          title: "欧洲清关专业能力",
          copy:
            "覆盖欧盟与英国的专业清关支持，确保进口流程顺畅合规。"
        },
        {
          icon: Warehouse,
          title: "整合最后一公里派送",
          copy:
            "直连领先承运商网络和本地配送伙伴，实现高效末端派送。"
        },
        {
          icon: Globe2,
          title: "实时货件可视化",
          copy:
            "先进追踪工具提供端到端货件监控和完整供应链透明度。"
        },
        {
          icon: CheckCircle2,
          title: "灵活物流解决方案",
          copy:
            "为电商、零售和 B2B 供应链定制运输与派送选项。"
        },
        {
          icon: Clock3,
          title: "专属客户支持",
          copy:
            "响应迅速的物流专家在整个运输旅程中提供主动沟通和运营支持。"
        }
      ]
    },
    why: {
      eyebrow: "为什么选择 EPIX",
      title: "为什么选择 EPIX",
      copy:
        "EPIX 结合全球覆盖与本地专业能力，在欧洲提供无缝电商物流解决方案，包括清关、运输以及可靠的最后一公里派送服务。",
      points: [
        "广泛的欧洲网络",
        "端到端物流解决方案",
        "可靠的清关专业能力",
        "灵活的运输选择",
        "值得信赖的最后一公里派送伙伴",
        "专属本地支持团队",
        "快速响应与卓越运营",
        "实时货件追踪与轨迹可视化"
      ]
    },
    contact: {
      eyebrow: "联系",
      title: "和 EPIX 讨论你的下一票空运货物。",
      email: "hello@epix-logistics.com",
      phone: "+31 684747361",
      location: "全球空运服务台"
    },
    partners: {
      label: "合作伙伴"
    }
  }
};

type LandingPageClientProps = {
  initialLocale: Locale;
};

export default function LandingPageClient({
  initialLocale
}: LandingPageClientProps) {
  const router = useRouter();
  const languageSelectorRef = useRef<HTMLDivElement>(null);
  const [locale, setLocale] = useState(initialLocale);
  const [isLanguageMenuOpen, setIsLanguageMenuOpen] = useState(false);
  const copy = landingContent[locale];

  useEffect(() => {
    async function redirectIfLoggedIn() {
      try {
        await getCurrentUser();
        router.replace("/waybills");
      } catch {
        // Public visitors stay on the EPIX landing page.
      }
    }

    void redirectIfLoggedIn();
  }, [router]);

  useEffect(() => {
    document.documentElement.lang = localeToHtmlLang(locale);
  }, [locale]);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (
        languageSelectorRef.current &&
        !languageSelectorRef.current.contains(event.target as Node)
      ) {
        setIsLanguageMenuOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsLanguageMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function handleLocaleChange(nextLocale: Locale) {
    setLocale(nextLocale);
    setIsLanguageMenuOpen(false);
    document.cookie = `${LANGUAGE_COOKIE}=${nextLocale}; path=/; max-age=31536000; SameSite=Lax`;
  }

  const languageOptions = [
    {
      locale: "en" as const,
      label: copy.language.english,
      shortLabel: copy.language.englishShort
    },
    {
      locale: "zh" as const,
      label: copy.language.chinese,
      shortLabel: copy.language.chineseShort
    }
  ];

  return (
    <main className={styles.page} id="home">
      <header className={styles.navbar}>
        <Link className={styles.brand} href="/" aria-label="EPIX home">
          <Image
            alt=""
            aria-hidden="true"
            className={styles.brandLogo}
            height={46}
            src="/brand/epix.jpg"
            width={156}
          />
        </Link>
        <nav className={styles.navLinks} aria-label={copy.nav.label}>
          <a href="#home">{copy.nav.home}</a>
          <a href="#services">{copy.nav.service}</a>
          <a href="#why-epix">{copy.nav.why}</a>
          <a href="#contact">{copy.nav.contact}</a>
        </nav>
        <div className={styles.navActions}>
          <div className={styles.languageSelector} ref={languageSelectorRef}>
            <button
              aria-expanded={isLanguageMenuOpen}
              aria-haspopup="menu"
              aria-label={copy.language.buttonLabel}
              className={styles.languageButton}
              onClick={() => setIsLanguageMenuOpen((isOpen) => !isOpen)}
              type="button"
            >
              <Languages aria-hidden="true" size={17} />
              <span className={styles.languageCode}>
                {locale === "zh"
                  ? copy.language.chineseShort
                  : copy.language.englishShort}
              </span>
              <ChevronDown
                aria-hidden="true"
                className={styles.languageChevron}
                size={15}
              />
            </button>
            {isLanguageMenuOpen && (
              <div className={styles.languageMenu} role="menu">
                {languageOptions.map((option) => (
                  <button
                    aria-checked={locale === option.locale}
                    className={styles.languageOption}
                    key={option.locale}
                    onClick={() => handleLocaleChange(option.locale)}
                    role="menuitemradio"
                    type="button"
                  >
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.shortLabel}</small>
                    </span>
                    <Check aria-hidden="true" className={styles.languageCheck} size={16} />
                  </button>
                ))}
              </div>
            )}
          </div>
          <Link className={styles.loginButton} href="/login">
            {copy.nav.login}
          </Link>
        </div>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroOverlay} />
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>{copy.hero.eyebrow}</p>
          <h1>{copy.hero.title}</h1>
          <p className={styles.heroCopy}>{copy.hero.copy}</p>
          <div className={styles.heroActions}>
            <a className={styles.primaryCta} href="#services">
              {copy.hero.primaryCta}
              <ArrowRight aria-hidden="true" size={18} />
            </a>
            <a className={styles.secondaryCta} href="#contact">
              {copy.hero.secondaryCta}
            </a>
          </div>
        </div>
      </section>

      <section className={styles.metrics} aria-label={copy.metricsLabel}>
        {copy.metrics.map((metric) => {
          const Icon = metric.icon;

          return (
            <div key={metric.title}>
              <Icon aria-hidden="true" size={22} />
              <strong>{metric.title}</strong>
              <span>{metric.copy}</span>
            </div>
          );
        })}
      </section>

      <section className={styles.section} id="services">
        <div className={styles.sectionHeader}>
          <p className={styles.eyebrow}>{copy.services.eyebrow}</p>
        </div>
        <div className={styles.serviceGrid}>
          {copy.services.cards.map((service) => {
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

      <section className={styles.whySection} id="why-epix">
        <div className={styles.sectionHeader}>
          <p className={styles.eyebrow}>{copy.why.eyebrow}</p>
          <h2>{copy.why.title}</h2>
          <p>{copy.why.copy}</p>
        </div>
        <ul className={styles.whyChecklist}>
          {copy.why.points.map((point) => (
            <li key={point}>
              <CheckCircle2 aria-hidden="true" size={19} />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer className={styles.contactFooter} id="contact">
        <div>
          <p className={styles.eyebrow}>{copy.contact.eyebrow}</p>
          <h2>{copy.contact.title}</h2>
        </div>
        <div className={styles.contactGrid}>
          <span>
            <Mail aria-hidden="true" size={18} />
            {copy.contact.email}
          </span>
          <span>
            <Plane aria-hidden="true" size={18} />
            {copy.contact.phone}
          </span>
          <span>
            <MapPin aria-hidden="true" size={18} />
            {copy.contact.location}
          </span>
        </div>
      </footer>

      <section className={styles.partnerBand} aria-label={copy.partners.label}>
        <div className={styles.partnerLogos}>
          {partnerLogos.map((partner) => (
            <div
              aria-label={partner.name}
              className={`${styles.partnerLogo} ${partner.className}`}
              key={partner.name}
            >
              <span aria-hidden="true">{partner.name}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
