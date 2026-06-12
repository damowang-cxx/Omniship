"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { getCurrentUser, login } from "@/lib/api";
import styles from "./page.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function redirectIfLoggedIn() {
      try {
        await getCurrentUser();
        router.replace("/waybills");
      } catch {
        // Stay on login page when there is no active session.
      }
    }

    void redirectIfLoggedIn();
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await login(email, password);
      router.replace("/waybills");
    } catch {
      setErrorMessage("邮箱或密码不正确，或账号已被禁用。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel}>
        <div className={styles.brand}>
          <span>EPIX Logistics</span>
          <h1>登录</h1>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label>
            <span>邮箱</span>
            <input
              autoComplete="email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          <label>
            <span>密码</span>
            <input
              autoComplete="current-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {errorMessage && <p className={styles.error}>{errorMessage}</p>}

          <button disabled={isSubmitting} type="submit">
            <LogIn aria-hidden="true" size={18} />
            {isSubmitting ? "登录中" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
