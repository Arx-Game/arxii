<!-- evidence-answer -->
Evidence for the two open items on PR #5143 (issue #5140), re-run after the fix in commit 00d74d15d (the server reports revision 00d74d15d). Fresh throwaway database `rt_5140b`, its own server (ports 4001 and 4002), and the Vite dev server on port 3000 proxying `/api` to 4001. Signed in as `e2e_test_account` through the real login form, in headless Chromium. Items 6 and 7 ran in the same browser session.

## Item 6: same-origin absolute `next` links are still followed

**Verdict: PASS.**

**What I did.** Seeded 25 `PlayerMail` rows for `e2e_test_account` (the mail page size is 20, so the list has two pages). In the signed-in page I ran `page.evaluate(() => import('/src/lib/pagination.ts'))` and called `fetchAllPages('/api/roster/mail/', ...)`.

**What I expected.** The call returns all 25 rows. The network log shows page 1 and then `http://localhost:3000/api/roster/mail/?page=2`, both 200, with no refusal.

**What I saw.** The call returned 25 rows, with the first row "Mail 24" and the last "Mail 00":

    ITEM 6 RESULT: {"outcome":"ok","rowCount":25,"firstSubject":"Mail 24","lastSubject":"Mail 00"}

The network log for the call:

    REQUEST  GET http://localhost:3000/api/roster/mail/
    RESPONSE 200 GET http://localhost:3000/api/roster/mail/
    REQUEST  GET http://localhost:3000/api/roster/mail/?page=2
    RESPONSE 200 GET http://localhost:3000/api/roster/mail/?page=2

No refusal appears. The failure from the first run is gone: that run's `next` link named `localhost:4001`, and it is now followed on the page's origin.

**Files.** `rerun-network-log-items-6-and-7.txt` (the ITEM 6 lines), `item6-fixed-signed-in.png`, `rerun-browser-console.txt`.

## Item 7: a URL on another origin is refused and nothing is sent

**Verdict: PASS.**

**What I did.** In the same signed-in session, imported `/src/evennia_replacements/api.ts` and called `apiFetch('https://evil.example/api/x/')`. The Playwright network log covers the whole run.

**What I expected.** The promise rejects with "Refusing to send a request off this site". The network log has no request to `evil.example` during that call.

**What I saw.**

    ITEM 7 RESULT: {"outcome":"rejected","message":"Refusing to send a request off this site: https://evil.example"}

The log window between `ITEM 7 START` and `ITEM 7 RESULT` holds only those two markers, with no request lines. The page stayed on `http://localhost:3000/`.

**Files.** `rerun-network-log-items-6-and-7.txt` (the ITEM 7 lines), `item7-fixed-refused.png`, `rerun-browser-console.txt`.

## Files in docs/reviews/5140b/

- `evidence-answer.md` (this file)
- `expected.txt` (expected results; the re-run section was written before the re-run)
- `rerun-network-log-items-6-and-7.txt` (raw request and response log for the re-run)
- `rerun-browser-console.txt` (browser console output for the re-run)
- `item6-fixed-signed-in.png`
- `item7-fixed-refused.png`
- `run1-evidence-answer.md`, `run1-network-log-items-6-and-7.txt`, `run1-item6-signed-in.png`, `run1-item7-refused.png` (the first run, before the fix, kept for the record; item 6 failed there)
