# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public GitHub issue.

Use GitHub's [private vulnerability reporting](https://github.com/yevhen-kalyna/autoria-mcp/security/advisories/new)
("Report a vulnerability" under the repository's **Security** tab), or email
<yevhen.kalyna@gmail.com>.

Please include enough detail to reproduce the issue (affected version, steps,
and impact). This is a small volunteer project, so response times are
best-effort; you'll get an acknowledgement as soon as possible.

## Handling credentials

`autoria-mcp` talks to the AUTO.RIA API using two secrets supplied via environment
variables: `AUTORIA_API_KEY` and (for the paid endpoints) `AUTORIA_USER_ID`.

- **Never commit credentials.** `.env` and `.env.*` are gitignored; only
  `.env.example` (a placeholder template) is tracked. Captured API responses under
  `research/` are gitignored because they can contain a `user_id`.
- The API key is held in a `pydantic.SecretStr`, sent only as a query parameter to
  the API host, and is never written to logs or `repr` output.
- If you accidentally expose a key, rotate it at <https://developers.ria.com> and,
  if it was committed, scrub it from git history (e.g. `git filter-repo`) — rotating
  the key is the important part, since the old value is already public.

## Supported versions

This project is pre-1.0; only the latest released version receives fixes.
