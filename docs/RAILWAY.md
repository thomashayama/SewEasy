# Railway deployment

One Railway service (this repo's Dockerfile) + the Postgres plugin.
`railway.toml` at the repo root sets the Dockerfile build, `/health`
healthcheck, and restart policy. The healthcheck timeout is generous
because the image is large (the Warp build) and cold starts are slow.

## Setup

1. Railway dashboard -> New Project -> Deploy from GitHub repo ->
   `thomashayama/SewEasy`. Railway picks up `railway.toml` automatically.
2. Add the Postgres plugin to the project and attach it to the service
   (it injects `DATABASE_URL`; the code normalizes `postgres://` ->
   `postgresql://`).
3. Set the service environment variables (below).
4. Networking -> Custom Domain (see below).

## Environment variables

| Var | Value |
|---|---|
| `DATABASE_URL` | Injected by the Postgres plugin |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console -> APIs & Services -> Credentials |
| `GOOGLE_CLIENT_SECRET` | Same |
| `GOOGLE_REDIRECT_URI` | `https://seweasy.thomashayama.com/auth/callback` |
| `APP_URL` | `https://seweasy.thomashayama.com` (controls Secure cookies) |
| `PORT` | Set by Railway automatically |

## Custom domain (seweasy.thomashayama.com)

1. Service -> Settings -> Networking -> Custom Domain ->
   `seweasy.thomashayama.com`. Railway shows a CNAME target
   (`<something>.up.railway.app`).
2. At the DNS provider for `thomashayama.com`, add:
   `CNAME  seweasy  ->  <that target>`. Railway provisions TLS
   automatically once the record resolves.
3. In the Google OAuth client, add
   `https://seweasy.thomashayama.com/auth/callback` to the authorized
   redirect URIs.

## Notes

- Single instance only: GUI sessions live in process memory and temp
  files on the container disk. Don't scale horizontally without rework.
- The schema is created by `create_all` at startup (no Alembic yet), so
  first boot against a fresh Postgres just works.
- Deploys are triggered by pushes to `main` (Railway's default).
