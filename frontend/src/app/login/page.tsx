"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  FileText,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Brand } from "@/components/shell";
import { useAuth } from "@/components/auth";
import { ErrorNotice } from "@/components/ui";
import { errorMessage } from "@/lib/api";
export default function LoginPage() {
  const { session, loading, login } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!loading && session) router.replace("/");
  }, [loading, session, router]);
  return (
    <div className="login-page">
      <section className="login-story">
        <Brand />
        <div className="login-story-content">
          <span className="eyebrow">Vendor operations, with oversight</span>
          <h1>
            Move work forward.
            <br />
            <span>Keep people in control.</span>
          </h1>
          <p>
            From the first document to the final approval, every decision has
            evidence and every action has a record.
          </p>
          <div className="process-preview">
            {[
              {
                icon: FileText,
                title: "Capture the request",
                text: "One place for context and documents",
              },
              {
                icon: Sparkles,
                title: "Extract & validate",
                text: "AI-assisted fields, deterministic checks",
              },
              {
                icon: ShieldCheck,
                title: "Review & authorize",
                text: "An independent approval before execution",
              },
            ].map(({ icon: Icon, title, text }, index) => (
              <div className="process-preview-row" key={title}>
                <span className="process-icon">
                  <Icon size={20} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <span>{text}</span>
                </div>
                <span className="process-number">0{index + 1}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="login-footer">
          <Check size={15} /> Verifiable evidence. Deliberate decisions.
        </p>
      </section>
      <section className="login-form-area">
        <div className="login-form-wrap">
          <div className="login-lock">
            <LockKeyhole size={23} />
          </div>
          <h2>Welcome back</h2>
          <p className="muted">Sign in to your operations workspace.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              setBusy(true);
              setError(undefined);
              try {
                await login(
                  String(data.get("email")),
                  String(data.get("password")),
                );
                router.replace("/");
              } catch (cause) {
                setError(errorMessage(cause));
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Email address
              <input
                type="email"
                name="email"
                autoComplete="username"
                required
                placeholder="you@company.com"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                maxLength={1024}
                placeholder="Enter your password"
              />
            </label>
            <ErrorNotice message={error} />
            <button className="button full" disabled={busy || loading}>
              {busy ? "Signing in…" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="login-help">
            Need access? Ask your workspace administrator to create an account.
          </p>
        </div>
      </section>
    </div>
  );
}
