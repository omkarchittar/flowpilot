# Operations console implementation

The console uses the authenticated API as its only product data source. App Router pages provide
navigation; client components own forms and polling. The same-origin `/api` rewrite forwards cookies
and browser Origin to FastAPI. CSRF tokens stay in memory; role/ownership authority remains server-side.

Visual direction: a quiet off-white workspace, ink-colored navigation, restrained violet actions,
readable status colors with text labels, generous spacing and compact evidence tables. Empty/loading/
error states must be useful without fabricated activity. Responsive navigation and keyboard focus are
part of the first implementation.

## Routes and acceptance

- Login: protected session, inline failures, recovery from expired sessions.
- Dashboard: persisted counts, recent requests, attention queue, links into work.
- Workflows/approvals: status filters, pagination, clear revision/state and ownership.
- New request: text plus bounded attachments; duplicate submission protected by a stable request key.
- Workflow: extracted fields/confidence/source links, validation issues, documents, decisions and
  timeline. Independent approver can approve/reject/request changes; owner/admin can revise eligible
  requests. Backend conflicts remain visible and never imply success.
- Audit: chronological events, redacted payloads, page-scoped integrity verification and pagination.
- Notifications: persisted in-app messages with read status.
- Team: admin-only account creation and role/active status management.

## Verification

Typecheck, lint and production build; browser tests against actual FastAPI/PostgreSQL and a controlled
HTTP model adapter. Cover login → upload → extraction → independent approval → completed state → inbox,
changes/revision, rejection, blocked/unauthorized controls, audit inspection and narrow viewport.
Inspect rendered screenshots and accessibility before using assets in release documentation. Controlled
browser fixtures do not establish live model accuracy. Release still requires separate provider,
Docker/deployment and artifact verification.
