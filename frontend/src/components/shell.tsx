"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bell,
  ChevronRight,
  ClipboardCheck,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "./auth";
import { ErrorNotice } from "./ui";
import { errorMessage } from "@/lib/api";
const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/workflows", label: "Requests", icon: Layers3 },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/notifications", label: "Inbox", icon: Bell },
];
export function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Activity size={22} strokeWidth={2.7} />
      </span>
      flowpilot<span className="brand-period">.</span>
    </span>
  );
}
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string>();
  const [leaving, setLeaving] = useState(false);
  const navigation =
    session?.user.role === "admin"
      ? [...links, { href: "/team", label: "Team", icon: Users }]
      : links;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {open && (
        <button
          aria-label="Close navigation"
          className="nav-scrim"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`sidebar ${open ? "is-open" : ""}`}
        aria-label="Main navigation"
      >
        <div className="sidebar-top">
          <Link
            href="/"
            onClick={() => setOpen(false)}
            aria-label="FlowPilot home"
          >
            <Brand />
          </Link>
          <button
            className="icon-button mobile-only"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <div className="workspace-label">
          <span className="workspace-avatar">O</span>
          <div>
            <strong>Operations</strong>
            <span>Vendor workspace</span>
          </div>
          <ChevronRight size={14} />
        </div>
        <p className="nav-caption">Workspace</p>
        <nav>
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              aria-current={
                pathname === href ||
                (href === "/workflows" && pathname.startsWith("/workflows/"))
                  ? "page"
                  : undefined
              }
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={22} />
          <strong>People stay in control.</strong>
          <p>Every vendor creation requires an independent human approval.</p>
        </div>
        <div className="sidebar-account">
          <span className="avatar">
            {session?.user.name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{session?.user.name}</strong>
            <span>{session?.user.role}</span>
          </div>
          <button
            className="icon-button"
            aria-label="Sign out"
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              try {
                await logout();
              } catch (e) {
                setError(errorMessage(e));
              } finally {
                setLeaving(false);
              }
            }}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-only"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {pathname === "/"
                ? "Overview"
                : pathname.startsWith("/requests")
                  ? "New request"
                  : pathname.startsWith("/workflows/")
                    ? "Workflow"
                    : (navigation.find((item) => item.href === pathname)
                        ?.label ?? "Operations")}
            </strong>
          </div>
          <div className="topbar-actions">
            <Link
              className="icon-button inbox-link"
              href="/notifications"
              aria-label="Open inbox"
            >
              <Bell size={19} />
            </Link>
            <Link href="/requests/new" className="button small">
              <Plus size={16} />
              New request
            </Link>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="main-content">
          <ErrorNotice message={error} />
          {children}
        </main>
        <footer className="app-footer">
          <span>FlowPilot · Accountable automation</span>
          <Link href="/workflows">
            View your requests <ArrowUpRight size={13} />
          </Link>
        </footer>
      </div>
    </div>
  );
}
