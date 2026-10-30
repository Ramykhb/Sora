# Authentication and authorization

All data APIs require `Authorization: Bearer <access_token>`. The shared `X-API-Key` mechanism has been removed. `/health`, OpenAPI and the public account entry points remain public; `/ready` and maintenance require an administrator. The static dashboard is still a disconnected UI demo.

## Setup and upgrade

From `backend`, using the existing virtual environment:

```sh
uv pip install -r requirements-dev.txt
alembic upgrade head
python -m scripts.manage_users create-admin admin@example.com --name 'Administrator'
```

The administrator password is prompted twice and is never placed in shell arguments. To promote an existing account, run `python -m scripts.manage_users promote person@example.com`. Registration always creates a regular user; no public endpoint lets users choose their role. These commands are trusted local administrative operations with database access.

Migration `0002_authentication` adds accounts, login sessions, one-time tokens, rate limits and capture ownership. Existing captures and CLI-created captures remain **unowned**, visible only to administrators. They are never silently assigned to the first person who registers. To explicitly assign one, run:

```sh
python -m scripts.manage_users claim-session person@example.com CAPTURE_SESSION_UUID
```

This only claims an unowned session; it cannot transfer someone else's capture. Install dependencies and migrate before restarting an existing API. Docker's app profile applies migrations automatically. No data volumes need to be reset. Downgrading removes the auth tables and owner links, so it discards account data.

## Register and log in

All paths below start with `/api/v1`.

```sh
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"replace-with-your-password","display_name":"Person"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"replace-with-your-password"}'
```

Registration returns a public user profile; login returns `access_token`, `refresh_token`, `token_type=bearer`, `expires_in`, `refresh_expires_at` and `user`. Replace example passwords. Passwords must be 12–128 characters when registering/changing/resetting. Emails are normalized to lowercase; profile email is immutable in this version. Unknown/incorrect/disabled login credentials return the same 401 response. Validation responses omit input values to avoid reflecting passwords or tokens.

Send the returned access token on protected requests:

```sh
curl http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $SORA_ACCESS_TOKEN"
curl http://localhost:8000/api/v1/sessions -H "Authorization: Bearer $SORA_ACCESS_TOKEN"
```

Swagger's **Authorize** button accepts the access token. Login is a JSON email/password API, not an OAuth authorization server or social-login integration.

## Token lifecycle

Passwords use salted Argon2id (64 MiB memory, 3 iterations, parallelism 2). Access and refresh tokens are cryptographically random opaque bearer values; only SHA-256 digests are stored. There is no JWT signing secret or shared API key to configure. The API checks the database on every authenticated request, so logout and account deactivation revoke access immediately for subsequent requests.

- Access lifetime: `AUTH_ACCESS_MINUTES`, default 15, maximum 60.
- Login-session lifetime: `AUTH_REFRESH_DAYS`, default 30, maximum 90. Refresh never extends this absolute deadline.
- `POST /auth/refresh`: JSON `{"refresh_token":"..."}` returns a new pair and immediately invalidates the previous access and refresh tokens.
- **Serialize refresh calls** in each client. Store the replacement pair atomically. Reusing an already consumed refresh token revokes its entire login session, including the latest pair. Concurrent duplicate refreshes are intentionally treated as reuse; do not retry a lost refresh response blindly. Sign in again.
- `POST /auth/logout`: revoke the current login; `POST /auth/logout-all`: revoke all of that user's logins. Both require an access token.
- `GET /auth/sessions`: list up to 100 active login sessions, including `is_current`; no token digests are exposed. `DELETE /auth/sessions/{id}` revokes one of your login sessions. Capture sessions and login sessions have separate IDs.
- `POST /auth/change-password`: `current_password`, `new_password`; revokes every login and recovery token. Sign in again afterwards.
- Expired login sessions and one-time tokens are removed by retention cleanup. Consumed refresh digests are retained for replay detection until their login session expires.

Use HTTPS/WSS outside local development. Mobile clients should keep tokens in OS secure storage. Browser clients can keep them in memory; an HttpOnly-cookie/BFF design would be a separate integration. This API uses explicit bearer headers, does not issue authentication cookies and does not accept tokens in URLs. Frontend token storage/refresh is not implemented by this backend change.

## Ownership and roles

A new capture session belongs to its authenticated creator. Regular users can only read/change/delete their own sessions, images, answers, feedback, alerts and live streams. Requests for another user's capture return 404. Session lists, dashboard data and metrics are scoped to the user. The global pending-deletion count is `null` for regular users. Administrators can inspect all retained captures, see global metrics, run cleanup/reconciliation, and manage accounts.

- `GET/PATCH /auth/me`: own profile; PATCH accepts `display_name`.
- `DELETE /auth/me`: JSON `{"password":"..."}` reauthenticates and deletes the user, login sessions, captures and associated metadata; image deletion uses the durable deletion outbox. Administrators must first be demoted by another administrator.
- `GET /auth/users?limit=50&offset=0`: administrator-only user listing.
- `PATCH /auth/users/{id}`: administrator-only `role` (`user`/`admin`), `is_active`. Role/status updates revoke that user's existing logins and stop their streams. Administrators cannot alter their own role/status through this endpoint.

## Camera and WebSocket authentication

Both WebSockets require this first text message within five seconds:

```json
{"access_token":"ACCESS_TOKEN_FROM_LOGIN"}
```

Use it at `/sessions/{id}/events` and `/sessions/{id}/stream/frames`, then wait for `type=ready`. Origin and capture ownership are checked. Old `api_key` messages are rejected. Authentication failure closes with code 1008. Producer messages are rechecked before ingestion; subscriptions are rechecked before every event or 10-second heartbeat. MJPEG authentication is rechecked about once per second. WebRTC producer and viewer authorization is rechecked every second. Clients refresh their individual media connections over authenticated HTTP every 20 seconds; failed/expired connections reconnect and renegotiate. Logging out, changing/resetting a password, deleting an account or deactivating/changing a role stops that user's producers.

## Email verification and recovery

Set these in `.env` (see `.env.example`):

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=Sora <no-reply@example.com>
SMTP_SECURITY=starttls
AUTH_PUBLIC_URL=http://localhost:3000
AUTH_REQUIRE_VERIFIED_EMAIL=false
```

`SMTP_SECURITY` accepts `starttls`, `ssl` (usually port 465), or `none` for a trusted local mail sandbox. Configure real SMTP credentials and a permitted sender for actual delivery. Passwords are not emailed. Unconfigured delivery returns 503 for send requests. Mail work runs after the HTTP response so SMTP latency does not expose account existence. Configured send requests always return the same 202 message for eligible and unknown accounts; transport failures are logged without secrets and leave the public response generic. Mail dispatch uses in-process background tasks; clients can request another message after a server interruption.

- Registration sends verification mail when SMTP is configured.
- `POST /auth/resend-verification`: JSON `email`.
- `POST /auth/verify-email`: JSON `token`; marks the account verified.
- `POST /auth/forgot-password`: JSON `email`.
- `POST /auth/reset-password`: JSON `token`, `new_password`; revokes every login and outstanding account token. The user must log in again.

One-time tokens expire after 30 minutes, are hashed in the database, and are restricted to their purpose. Successful use consumes them atomically. A reset request never returns a recovery token in its API response. Emails include both a future frontend link (`AUTH_PUBLIC_URL/reset-password?token=...` or `/verify-email?token=...`) and the token for testing via the API. Those frontend pages are not part of this backend implementation. Until they are built, copy the token from your mailbox into Swagger. Set `AUTH_REQUIRE_VERIFIED_EMAIL=true` to enforce verification at login and on protected requests; SMTP must be configured before registration can succeed in that mode. Local admin creation marks the trusted administrator verified.

## Abuse limits and deployment

Account endpoints enforce database-backed atomic, fixed 15-minute limits per client IP and, where appropriate, normalized account. Registration/send/password/delete requests generally allow 5 attempts, login/one-time token consumption 10, and refresh 60. Both successful and failed attempts count. 429 includes `Retry-After`. Limits survive process restarts and do not trust arbitrary `X-Forwarded-For` headers. If using a proxy, configure Uvicorn's trusted proxy addresses explicitly so `request.client` represents the correct client. Retention removes expired rate-limit rows. The existing single-API-worker requirement still applies to live streaming.

## Validation

Tests use real Argon2 hashing, token generation, a real SQLite database and local image storage. They cover registration/profile validation, password verification, role/ownership enforcement, session-scoped metrics, cross-user HTTP/WebSocket denial, logout/expiry/rotation/replay, concurrent refresh, single-use recovery, verification, account deletion and rate limits. AI models and email transport are substituted. A PostgreSQL deployment migration and real SMTP delivery still need to be exercised in the configured deployment.

References: [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [OWASP password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).
