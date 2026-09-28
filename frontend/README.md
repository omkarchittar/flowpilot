# FlowPilot console

Next.js App Router / TypeScript operations UI for the FastAPI workflow service. Dashboard,
request upload, revision tracking, independent approval, source documents, audit timeline,
inbox and account administration all use persisted API data.

## Run locally

Start PostgreSQL, migrate, bootstrap an administrator and start the API and worker using
[the root README](../README.md). Then, with Node.js 24:

```sh
npm ci
npm run dev
```

Open http://localhost:3001. The default upstream is http://127.0.0.1:8001. Set
`FLOWPILOT_API_URL` when starting development if your backend address differs.

For a production build:

```sh
FLOWPILOT_API_URL=http://127.0.0.1:8001 npm run build
HOSTNAME=127.0.0.1 npm start
```

`build` prepares the standalone server with its public/static assets; `start` runs that
server on port 3001. **The upstream URL is baked into the build.** Changing an environment
variable on an existing image does not rewrite it. Rebuild to change the backend address.
Docker Compose supplies `http://api:8000` as a build argument.

All browser API traffic goes through `/api` on the console's origin. Session cookies are
HttpOnly; CSRF tokens stay in memory and every command is authorized by FastAPI. Configure
`FLOWPILOT_ALLOWED_ORIGINS` to the exact public console origin. Production also requires
`FLOWPILOT_ENVIRONMENT=production` and HTTPS for secure cookies.

The proxy ceiling is 51 MB, covering the backend's maximum 50 MB policy plus multipart
headroom. `/api/request-options` supplies the actual configured attachment limit to the
form. The backend independently enforces size, document count and parser limits.

## Checks

```sh
npm run lint
npm run typecheck
npm run format:check
npx playwright install chromium
TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flowpilot_test' npm run test:e2e
```

The browser suite requires the backend virtualenv at `../backend/.venv`. Its database
role needs `CREATEDB`; it creates and removes a separate randomly named database. Tests
start actual migrations, FastAPI, a separate worker, a controlled HTTP model adapter and
the production standalone frontend. Ports 18081 and 3101 must be free. No real provider
credentials or business data are used.

Journeys cover upload → independent approval → completion → audit/inbox, missing evidence
and revisions, rejection/self-approval, ownership, team access, stale draft conflicts,
12 MB multipart uploads, responsive navigation and automated axe accessibility checks.
Screenshots and failure traces are in `test-results/`; the HTML report is in
`playwright-report/`. Controlled responses verify software behavior, not model accuracy.

ESLint is pinned to 9.39.5 because the current Next React rules fail under ESLint 10
(`context.getFilename` compatibility). Revisit this pin when the upstream rules support 10.
