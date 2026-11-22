# Panel bug fixes

Base: `2de3af1` from `faresbazed/Muse-ai`.

## Changes

- **Mailbox list privacy:** `/api/accounts` returns the metadata used by the table, rather than passwords, client IDs, refresh tokens, and private OTP URLs. Internal mailbox access is unchanged.
- **Credential imports:** changes to just a password or client ID are no longer skipped. Re-importing new credentials preserves `in_use` and `done` states and their timestamps. Failed mailboxes can still become available after corrected credentials are imported, with stale claim/failure metadata cleared. Explicit reset controls remain available.
- **Result filters:** live/invalid/unchecked filters read `live_check.status` rather than searching all stored JSON text. Unrelated diagnostic text no longer changes the result. Malformed legacy JSON does not crash filtering.
- **Invite reset safety:** an explicit empty `codes` list does nothing. Omitting `codes` keeps the existing repair-all behavior for invalid/exhausted codes with remaining capacity.
- **Pagination validation:** mailbox, invite, result, and run list endpoints require a positive limit of at most 1,000; paginated endpoints reject negative offsets. Defaults used by the panel are unchanged.
- **Stale-release validation:** the endpoint rejects ages below 60 seconds, including negative ages that previously released currently active mailboxes. The default remains 1,800 seconds.

## Verification

- Added 15 regression cases in `test_panel_regressions.py`.
- On the original source, 13 of these cases fail and 2 pass. On the fixed source, all 15 pass.
- Full pytest run: **18 passed** (15 new cases plus 3 existing tests).
- Existing standalone offline smoke scripts: **6/6 onboarding**, **9/9 runner**, **3/3 WebUI**.
- Repeated the full Python checks with socket connections disabled. No external registration, OTP, redemption, proxy test, or mail request was needed.
- Frontend production build passed; the generated assets were byte-for-byte unchanged. There are no frontend or visual changes in this patch.
- `git diff --check` passed.

Run locally in a virtual environment:

```sh
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
python test_onboarding_smoke.py
python test_runner_smoke.py
python test_webui_smoke.py
cd webui/frontend
npm ci
npm run build
```

The test environment emitted one upstream Starlette/httpx deprecation warning. It did not affect the results.

## Boundaries and compatibility

No schema migration is required. No live database or server was accessed, and no deployment is included. Existing credentials remain in SQLite as before. This patch is not a full security audit or a promise that every bug has been found.

The repository still has no built-in login, and stored credentials remain unencrypted. Keep the panel behind the access controls described in its README. Removing credentials from a table response does not make an unauthenticated panel safe to expose to the internet.

The new pagination bounds and metadata-only mailbox list are intentional API changes. The bundled frontend does not rely on the removed credential fields. External clients that previously used those fields or requested more than 1,000 rows per page would need updating.

The JSON filters use SQLite JSON functions; these were verified in the test environment. No deployment host was available to verify its SQLite build.
