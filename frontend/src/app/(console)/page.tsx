"use client";
import Link from "next/link";
import {
  ArrowRight,
  CheckCheck,
  CircleAlert,
  ClipboardCheck,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/components/auth";
import {
  ErrorNotice,
  Loading,
  PageHeading,
  Panel,
  TextLink,
} from "@/components/ui";
import { WorkflowTable } from "@/components/workflow-table";
import { useResource } from "@/lib/use-resource";
import { statusLabels, workingStates } from "@/lib/format";
import type { Overview, Page, State, Workflow } from "@/lib/types";
export default function Dashboard() {
  const { session } = useAuth();
  const overview = useResource<Overview>("/overview", 10000);
  const recent = useResource<Page<Workflow>>("/workflows?limit=6", 10000);
  const pending = useResource<Page<Workflow>>(
    "/workflows?status=PENDING_APPROVAL&limit=4",
    10000,
  );
  const count = overview.data;
  const active = count
    ? workingStates.reduce((n, state) => n + (count.counts[state] ?? 0), 0)
    : 0;
  const stats = [
    {
      label: "Total requests",
      value: count?.total,
      icon: Layers3,
      detail: `${active} processing`,
      tone: "ink",
    },
    {
      label: "Awaiting approval",
      value: count?.pending_approval,
      icon: ClipboardCheck,
      detail: "Ready for a human decision",
      tone: "violet",
    },
    {
      label: "Needs attention",
      value: count
        ? count.manual_review + (count.counts.NEEDS_INFORMATION ?? 0)
        : undefined,
      icon: CircleAlert,
      detail: "Information or review required",
      tone: "amber",
    },
    {
      label: "Completed",
      value: count?.completed,
      icon: CheckCheck,
      detail: "Approved and executed",
      tone: "green",
    },
  ];
  return (
    <>
      <PageHeading
        eyebrow="Operations overview"
        title={`Welcome, ${session?.user.name.split(" ")[0] ?? "there"}.`}
        description="A clear view of your vendor onboarding, from intake to completion."
      />
      <ErrorNotice message={overview.error} retry={overview.refresh} />
      <div className="stat-grid">
        {stats.map(({ label, value, icon: Icon, detail, tone }) => (
          <article className="stat-card" key={label}>
            <div>
              <span>{label}</span>
              <span className={`stat-icon ${tone}`}>
                <Icon size={18} />
              </span>
            </div>
            <strong>{value ?? "—"}</strong>
            <p>{count ? detail : "Loading workspace…"}</p>
          </article>
        ))}
      </div>
      <div className="dashboard-columns">
        <Panel
          title="Your workflow at a glance"
          subtitle="Current state of requests you can access"
        >
          <div className="state-summary">
            {count ? (
              <>
                {count.total ? (
                  <div className="distribution" aria-hidden="true">
                    {(Object.entries(count.counts) as [State, number][]).map(
                      ([state, n]) => (
                        <span
                          key={state}
                          className={`segment segment-${state}`}
                          style={{ flex: n }}
                        />
                      ),
                    )}
                  </div>
                ) : (
                  <p className="muted">
                    Submit a request to begin tracking your workflow.
                  </p>
                )}
                <div className="state-legend">
                  {(
                    [
                      "PENDING_APPROVAL",
                      "NEEDS_INFORMATION",
                      "NEEDS_MANUAL_REVIEW",
                      "COMPLETED",
                      "REJECTED",
                    ] as State[]
                  ).map((state) => (
                    <Link href={`/workflows?status=${state}`} key={state}>
                      <span className={`legend-dot segment-${state}`} />
                      {statusLabels[state]}
                      <strong>{count.counts[state] ?? 0}</strong>
                    </Link>
                  ))}
                </div>
              </>
            ) : !overview.error ? (
              <Loading />
            ) : null}
          </div>
        </Panel>
        <section className="review-card">
          <div className="review-orbit">
            <ShieldCheck size={34} />
          </div>
          <span className="eyebrow">Deliberate by design</span>
          <h2>
            A human decision.
            <br />A complete record.
          </h2>
          <p>
            Review source evidence and validation checks before authorizing a
            vendor. FlowPilot records what happened at every step.
          </p>
          <Link href="/approvals">
            Open approval queue <ArrowRight size={17} />
          </Link>
        </section>
      </div>
      <Panel
        title="Ready for review"
        subtitle="Validated requests waiting for an independent decision"
        action={<TextLink href="/approvals">View queue</TextLink>}
      >
        <ErrorNotice message={pending.error} retry={pending.refresh} />
        {pending.data ? (
          <WorkflowTable rows={pending.data.items} compact />
        ) : !pending.error ? (
          <Loading />
        ) : null}
      </Panel>
      <Panel
        title="Recent requests"
        subtitle="The latest activity in your workspace"
        action={<TextLink href="/workflows">All requests</TextLink>}
      >
        <ErrorNotice message={recent.error} retry={recent.refresh} />
        {recent.data ? (
          <WorkflowTable rows={recent.data.items} />
        ) : !recent.error ? (
          <Loading />
        ) : null}
      </Panel>
    </>
  );
}
