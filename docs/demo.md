# Recorded product demonstration

The GIF in the README records the production Next.js console with FastAPI, a separate worker and disposable PostgreSQL. A requester submits fictional vendor documents; a different approver reviews evidence and the advisory AI brief, authorizes execution and inspects the verified audit trail. The requester then sees the resulting in-product notification.

All identities and documents are fictional. Model responses come from the **controlled local browser fixture**, not a live model. The application still performs actual extraction validation, revision checks, independent approval, transactional vendor creation, audit hashing and persisted notifications. No product response is substituted in the frontend. Only resize/palette conversion is applied to the recording.

To regenerate, install frontend/backend development dependencies and Chromium, then from `frontend`:

```sh
TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flowpilot_test' npm run record:demo
node scripts/render-demo.mjs test-results/demo-record-independent-vendor-approval-and-audit-demo/demo.webm
```

The database role needs CREATEDB. The fixture uses a disposable encryption key and hardcoded fictional account passwords, then removes temporary server/database state. State assertions determine readiness; short pauses allow viewers to read. No live provider key is needed.

Recording uses [Playwright video capture](https://playwright.dev/docs/videos). FFmpeg must support GIF encoding; `FFMPEG_BIN` can point to an alternate executable. The committed GIF uses FFmpeg 7.1, 8 fps, 960-pixel width and 128 colors. This is a reproducible integration demonstration, not extraction-accuracy evidence or production performance measurement.
