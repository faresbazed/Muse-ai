# Mobile and Arabic improvements

This follows the backend fixes in `80708b9`. It does not deploy or change registration/account behavior.

## Mobile layout

- Phone navigation is an off-canvas menu, with a backdrop, Escape-to-close, route-change closing, focus on menu entry, and background scroll locking.
- The Arabic menu slides from the right. Desktop navigation still supports collapsing.
- Narrow-screen headers use the current page title, without crowded desktop status pills or search controls.
- Flex/grid containers no longer force the document wider than the viewport. Dense status summaries become single-column on phones.
- Forms, advanced name/date fields, footer actions and dialogs fit narrow screens; buttons and selections have larger touch targets.
- Tables keep horizontal scrolling rather than crushing every column. A phone-only hint explains the gesture.

## Arabic

- Shorter, natural labels replace literal terms for navigation, account states and proxy management.
- Invitation activation and authentication tokens use distinct wording.
- Dynamic counts, destructive-action confirmations, provider metadata, advanced controls, clipboard messages and the empty-log message are translated.
- Menu search uses Arabic labels when Arabic is selected. Switching back to Chinese restores Chinese; API enum values and saved data are unchanged.
- Arabic layout keeps email addresses, URLs, identifiers and credentials isolated left-to-right. Dates follow the selected UI locale.
- Actual diagnostic log lines and credential contents remain unmodified. This is intentional, so diagnostic evidence and stored values are not rewritten by translation.

## Checks

The browser checks use only fixture data. Every request is intercepted locally; non-panel origins are blocked. The checks assert that inspection performs no API writes.

- All ten panel routes at 390px phone and 1440px desktop widths in Arabic.
- Additional 320px narrow-phone, 820px tablet and Chinese-desktop checks.
- No document-width overflow or uncaught browser errors in those 23 route/viewport cases.
- Mobile menu opening, closing with Escape, and closing after navigation.
- Advanced forms, actual provider-field definitions, credential dialogs, and cancelling destructive-action confirmations.
- Arabic/Chinese switching, Arabic menu search and dark mode.
- Three translation unit-test groups, plus the existing 18 Python tests.
- Compatible dependency updates cleared the npm audit findings present in the old lockfile. Audit results are time-sensitive, not a security guarantee.

Run from `webui/frontend`:

```sh
npm ci
npm test
npx playwright install chromium
npm run test:ui
```

To use an already installed Chrome instead of Playwright's Chromium:

```sh
BROWSER_EXECUTABLE_PATH=/path/to/chrome npm run test:ui
```

The build runs before browser checks. Screenshots and a JSON check summary are written to `webui/frontend/test-results/`, which is ignored by Git. Rebuilt production assets are included under `webui/static/`.

The panel's existing authentication and credential-storage warnings still apply. No live server or production dataset was used for these checks.
