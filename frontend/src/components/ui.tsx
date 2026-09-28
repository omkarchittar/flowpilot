import Link from "next/link";
import {
  ArrowRight,
  Check,
  CircleAlert,
  Inbox,
  LoaderCircle,
} from "lucide-react";
import type { State } from "@/lib/types";
import { statusLabels, workingStates } from "@/lib/format";
export function Status({ value }: { value: State }) {
  const tone =
    value === "COMPLETED"
      ? "success"
      : value === "REJECTED"
        ? "danger"
        : ["NEEDS_INFORMATION", "NEEDS_MANUAL_REVIEW"].includes(value)
          ? "warning"
          : value === "PENDING_APPROVAL"
            ? "violet"
            : "neutral";
  return (
    <span className={`status ${tone}`}>
      <span
        className={
          workingStates.includes(value) ? "status-dot pulse" : "status-dot"
        }
      />
      {statusLabels[value]}
    </span>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message?: string | null;
  retry?: () => void;
}) {
  if (!message) return null;
  return (
    <div className="notice danger" role="alert">
      <CircleAlert size={18} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={20} />
      {label}
    </div>
  );
}
export function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Inbox size={25} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function SuccessNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="notice success" role="status">
      <Check size={18} />
      <span>{children}</span>
    </div>
  );
}
export function TextLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link className="text-link" href={href}>
      {children}
      <ArrowRight size={15} />
    </Link>
  );
}
export function Pagination({
  offset,
  total,
  limit,
  onChange,
}: {
  offset: number;
  total: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total === 0
          ? "No requests"
          : `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`}
      </span>
      <div className="button-row">
        <button
          className="button small secondary"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          className="button small secondary"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
