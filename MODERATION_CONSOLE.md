# Moderation console (2026-09-06 release work)

The `/moderation` page and `/api/v1/moderation/reports` proxy require User
`cd25861e7f533f006bfce7b539b9adfcb6487554` or a compatible later build (V026).
The first release pinned to User `46fbd0d9` does not provide these endpoints.

Every moderation request, including a read by an owner, requires an explicit
`X-Map-Environment`. The registered target is selected by existing context-local
configuration. The console never queries a serving DB directly. Control account
and audit storage remain on the independent control DB and use the existing
separate migration/runtime roles. An unavailable target does not block login.

| Role | List receipt metadata | Read report/message and review | Hide/restrict/lift |
|---|---|---|---|
| viewer | Allowed environment only | No | No |
| operator | Allowed environment only | Yes | No |
| owner | Explicitly selected environment | Yes | Yes |

`REVIEW` starts investigation. `DISMISS` closes a report without finding a violation.
`RESOLVE` records that human handling is complete (for example, correcting a
misleading generated recommendation through the service team's normal workflow).
Those codes do not themselves modify an AI model, itinerary or image.
`HIDE_CHAT_MESSAGE` hides one message across REST and WebSocket delivery.
`RESTRICT_CHAT` prevents that author from sending in every room for 1..720 hours.
`LIFT_CHAT_RESTRICTION` releases the author's current restriction; the UI asks the
operator to check other reports first because the restriction applies to the user.

Before a write, the existing cookie/session + custom environment-header protection
and audit availability check run. Detail access is also audited before content is
read. Audit and the User `X-Admin-Actor` receive an opaque `admin_<control account id>`;
no report/message text or upstream response body is copied into the control audit.
The internal token is added by the server and is not exposed to the browser.
Upstream/network/validation failures return fixed text without original bodies.

The UI renders original text through React escaping, keeps it out of browser
persistent storage, disables mutations while pending, confirms scope and effect,
uses the same action UUID when retrying an ambiguous failure, and refetches status
on completion/failure. Closing the detail removes that query's cached original.
The backend remains authoritative for role, environment and status enforcement.

User V026 owns retention: completed report descriptions/fingerprints/target refs
are scrubbed at 90 days; User actions expire 365 days after creation; completed
receipt metadata expires 365 days after completion when no actions remain. Its
hourly worker handles at most 500 rows per operation and may defer physical removal
past the threshold. This console does not delete existing central audit records.

Validation: Python auth/role/environment/audit-failure/error-redaction tests;
`npm run build`; `tests/browser-moderation.cjs` with a synthetic HTTP fixture
(requires Playwright and the compiled web/dist). The release runtime evidence also
contains a separate real Admin control DB + Admin proxy + User PostgreSQL/Redis/JAR
trial. Browser fixture evidence and real proxy evidence are reported separately.
No GCP/NCP deployment or real-account operation is implied by these local checks.
