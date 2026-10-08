# Review evidence

- Reviewed revision: `1ec451b3feddabe186b601cf0520865cac496f47`
- Reviewer: the implementing agent (Claude Code), with the Playwright harness on the real production bundle; no demo link on the issue, so no demo-fidelity pass
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4186
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900, the default light theme
- Approved design: the ruling on issue #4195 (ApostateCD, 2026-10-08): option B, the fallback's "Go home" is a hard navigation so the root boundary depends on nothing above it. The fixture is the one that found the defect while #4193's evidence was written.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The root boundary's card after a chrome error: the error's own message, Try again, Go Home, Reload](docs/reviews/4195/01-root-fallback-1280.png)
- Comparison notes: With every list the Layout chrome asks for on load answered as a paginated object, a chrome component throws ("r.find is not a function" in the minified bundle) and the root boundary catches it. The card renders with the thrown message and its three buttons; the page is not blank, and the page errors raised contain nothing naming the Router. Clicking Go Home loads / afresh. On main the same fixture produced the blank page and the page error saying useNavigate may be used only in the context of a Router component (recorded in #4194's evidence thread, 2026-10-08, before the sheet fixture was corrected).
- Tested interactions: open `/characters/1` with the chrome-crashing fixture; read the card and the page errors; click Go Home and read the URL.
- Fixture/live boundary: the page, router, Layout chrome, root boundary and bundle are real. Every `/api/**` response is a fixture: the account, one roster entry, and a paginated page object for every other GET, which is what makes the chrome throw. The unit test `ErrorBoundary.test.tsx` renders the fallback with no Router above it (the root mount's shape) and asserts the hard navigation.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| The card renders after a chrome error (not a blank page) | "Something went wrong" with the error's message | MATCH | docs/reviews/4195/01-root-fallback-1280.png |
| Three recovery buttons | Try again, Go Home, Reload | MATCH | docs/reviews/4195/01-root-fallback-1280.png |
| No page error names the Router | none | MATCH | the spec's assertion at this revision |
| Go Home loads / afresh | URL path is / | MATCH | the spec's assertion at this revision |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-fallback-depends-on-nothing-above-it | PASS | `ErrorBoundary.tsx` has no `useNavigate`; `ErrorBoundary.test.tsx` "renders the fallback with no Router above it"; the capture | issue #4195, option B |
| R02-go-home-is-a-hard-navigation | PASS | `ErrorBoundary.test.tsx` "loads / afresh when Go Home is clicked" (`window.location.assign('/')`); the spec's URL assertion | issue #4195, option B |
| R03-root-boundary-stays-at-the-root | PASS | `main.tsx` unchanged; the fallback now renders there, as the capture shows | issue #4195, option B over A |
| R04-reviewer-agent | PASS | `tools/agents/fallback-provider-reviewer.md`; README row; `frontend/CLAUDE.md` error-boundary note | CLAUDE.md, Reviewer Agents |

## Unresolved findings

- None
