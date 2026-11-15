<!-- evidence-answer -->
Evidence for the two open items on PR #5143 (issue #5140). Head commit 087948757. Run on a throwaway database `rt_5140b`, its own server (ports 4001 and 4002), and the Vite dev server on port 3000 proxying `/api` to 4001. Signed in as `e2e_test_account` through the real login form, in headless Chromium.

## Item 6: same-origin absolute `next` links are still followed

**Verdict: FAIL on the dev-server path.**

**What I did.** Seeded 25 `PlayerMail` rows for `e2e_test_account` (the mail page size is 20, so the list has two pages). In the signed-in page I called the real `apiFetch` on `/api/roster/mail/`, then the real `fetchAllPages` from `frontend/src/lib/pagination.ts`, both loaded through Vite's `/src/...` URLs.

**What I expected.** Page 1 returns 200 with an absolute `next`. The request to that `next` URL goes to the page's own origin and returns 200. `fetchAllPages` returns all 25 rows.

**What I saw.** Page 1 returned 200 with 20 rows, a total count of 25, and this `next`:

    ITEM 6 RESULT: {"firstStatus":200,"firstCount":20,"firstNext":"http://localhost:4001/api/roster/mail/?page=2","firstCountTotal":25,"fetchAllError":"Refusing to send a request off this site: http://localhost:4001"}

The network log shows only the two page-1 requests, and no page-2 request:

    REQUEST  GET http://localhost:3000/api/roster/mail/
    RESPONSE 200 GET http://localhost:3000/api/roster/mail/
    REQUEST  GET http://localhost:3000/api/roster/mail/
    RESPONSE 200 GET http://localhost:3000/api/roster/mail/

`fetchAllPages` rejected with "Refusing to send a request off this site: http://localhost:4001" before it sent anything.

**Cause, as far as I can tell.** The Vite proxy in `frontend/vite.config.ts` sets `changeOrigin: true`, so Django sees host `localhost:4001`, and DRF builds the `next` link on that host. The page is on `localhost:3000`, so the new same-origin check refuses the link. The check is doing what it was written to do. The gap is that a `next` link built on a different host than the page is treated as foreign. I did not test a production topology, where the public proxy may or may not forward the `Host` header. That remains unverified.

**Note on my expectation.** My expected-results file assumed the `next` link would sit on the page's origin. It did not, on this proxy.

**Files.** `network-log-items-6-and-7.txt` (the ITEM 6 lines), `item6-signed-in-after-mail-pages.png`, `browser-console.txt`, `expected.txt`.

## Item 7: a URL on another origin is refused and nothing is sent

**Verdict: PASS.**

**What I did.** On the signed-in page, imported `/src/evennia_replacements/api.ts` and called `apiFetch('https://evil.example/api/x/')`. The Playwright network log covers the whole run.

**What I expected.** The promise rejects with "Refusing to send a request off this site". The network log has no request to `evil.example` during that call.

**What I saw.**

    ITEM 7 RESULT: {"outcome":"rejected","message":"Refusing to send a request off this site: https://evil.example"}

The log window between `ITEM 7 START` and `ITEM 7 RESULT` holds no request lines at all. The page stayed on `http://localhost:3000/`.

As a control, I ran a raw `fetch('https://evil.example/control')` outside `apiFetch`. The log recorded it, so the log would catch such a request:

    REQUEST  GET https://evil.example/control
    FAILED   https://evil.example/control net::ERR_NAME_NOT_RESOLVED

**Files.** `network-log-items-6-and-7.txt` (the ITEM 7 and CONTROL lines), `item7-refused-foreign-origin.png` (taken after the refusal; it is byte-identical in size to the item 6 screenshot, since both show the same signed-in page), `browser-console.txt`.

## Files in docs/reviews/5140b/

- `evidence-answer.md` (this file)
- `expected.txt` (expected results, written before the run)
- `network-log-items-6-and-7.txt` (raw Playwright request and response log)
- `browser-console.txt` (browser console output)
- `item6-signed-in-after-mail-pages.png`
- `item7-refused-foreign-origin.png`
