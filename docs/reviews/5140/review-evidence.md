# Review evidence

- Reviewed revision: e5929b4ca21a75a2ab9a5eb4ebf6e8fe418f1b94
- Reviewer: real-testing pass (Haiku), own server on rt_5140
- Reviewer verdict: PASS
- Application/build identity: branch feature-5140-apifetch-refuses-a-url-on-another-origin, commit e5929b4ca21a75a2ab9a5eb4ebf6e8fe418f1b94, `just fe-build` bundle (largest chunk assets/index-BkjAs3VR.js, copied to src/web/static/dist)
- Environment: Form B, Postgres database rt_5140 (dropped after the pass), Evennia server on :4001 (web) and :4002 (websocket), Chromium for Testing 145.0.7632.6 (headless shell, cached build 1208, because the pinned Playwright build was not installed), social-login credentials removed from the server environment to match CI
- Viewports/themes: Playwright default desktop viewport 1280x720, light theme (system default)
- Approved design: not applicable (no demo; non-visual security fix, issue #5140)
- Visual review: not applicable (the change has no visual surface)
- Visual verdict: NOT_APPLICABLE
- Screenshots: ![signed in](docs/reviews/5140/signed-in-home.png) ![account](docs/reviews/5140/account-page.png)
- Comparison notes: Expected sign-in to succeed, the account page to show the account's data, and no request to fail with "Refusing to send a request off this site". Seen: sign-in succeeded and landed on the signed-in home (Your Characters, Your Attention, Time, Occasions, The Crier panels). The account page showed the email e2e_test@example.com with a Verified badge, and the password and email forms. The paginated mail list (Profile, Mail) returned HTTP 200 with the pagination shape (count 0, next null, previous null, empty results), because no mail is seeded, so no second page was reached. The phrase "Refusing to send a request off this site" appeared in no browser console message, and in none of the server, portal or HTTP request logs. The browser console showed three "Failed to load resource" messages for Google Fonts, which this sandbox cannot reach. The server log showed one traceback from the game clock's scheduled task magic.anima_regen_daily, which looks up a mechanics Property row that a fresh database does not seed. That task runs outside the web path and this change does not touch it. Expected and seen match for every interaction below. The refusal branch itself (a URL on another origin) was not triggered from the live site, because no normal page sends one; it is covered by the commit's unit tests only.
- Tested interactions: (1) Sign in as e2e_test_account through the login form: expected the signed-in home; saw / with the signed-in dashboard, login POST 200, GET /api/user/ 200, PASS. (2) Open /profile/account signed in: expected the account email; saw e2e_test@example.com with Verified, PASS. (3) Change password, sign in with the new one, restore it (account-settings spec): expected success both ways; spec passed, PASS. (4) Enrol TOTP, see ten recovery codes, turn TOTP off (account-settings spec): expected all three steps; spec passed, recovery-codes GET 200 and TOTP DELETE 200, PASS. (5) Visitor homepage, registration page, login page, registration validation, duplicate-username refusal, wrong password (user-journey spec, 15 tests): expected pages render and refusals show without a crash; all passed, wrong-password login returned 401, PASS. (6) Register a new account through the form: expected redirect to the email verification page; spec passed, signup returned 401 with a pending email-verification flow, which the frontend treats as success, PASS. (7) Profile, Mail, paginated list GET /api/roster/mail/?page=1: expected 200 with the pagination envelope; saw 200, count 0, empty results, no second page available, PASS. (8) Search all browser console messages and the server, portal and HTTP logs for the refusal text: expected none; none found, PASS.
- Fixture/live boundary: live server and real browser; rows seeded by seed_test_account (e2e_test_account, e2e_test@example.com) and the registration config opened on the throwaway database, as CI does. No factory rows. The rt_5140 database was dropped after the pass.

## Requirement ledger

| id | status | evidence | authorized decision |
|---|---|---|---|
| sign-in-live | PASS | Login form signed in e2e_test_account; POST auth/login 200; landed on signed-in home (screenshot signed-in-home.png) | none needed |
| account-data-live | PASS | /profile/account showed e2e_test@example.com Verified (screenshot account-page.png) | none needed |
| no-refusal-logged | PASS | Text "Refusing to send a request off this site" absent from browser console and server, portal and HTTP logs | none needed |
| paginated-list-live | PASS | Profile Mail list: GET /api/roster/mail/?page=1 200, count 0, empty results; no second page reachable | none needed |
| account-security-live | PASS | Password change and TOTP enrol/disable specs passed against the live server | none needed |

- Overall outcome: PASS

## Unresolved findings

None
