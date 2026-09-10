# Review evidence

- Reviewed revision: `<40-character commit SHA>`
- Reviewer: `<local reviewer agent or named reviewer>`
- Reviewer verdict: `<PASS only after the reviewer completes the comparison>`
- Application/build identity: `<production build, preview URL, or test run>`
- Environment: `<OS, browser, backend, and relevant configuration>`
- Viewports/themes: `<each viewport and theme compared>`
- Approved design: `<issue/spec/demo URL, or Not applicable with reason>`
- Visual review: `<Completed or Not applicable with reason>`
- Visual verdict: `<PASS or NOT_APPLICABLE>`
- Screenshots: `<Markdown image links to GitHub PR/issue attachments or other durable URLs>`
- Comparison notes: `<what was compared and concrete discrepancies, or Not applicable>`
- Tested interactions: `<ordinary user path, including failure/reconnect paths>`
- Fixture/live boundary: `<what used fixtures and what reached a live backend>`
- Overall outcome: `<PASS only when every mandatory criterion passes>`

## Visual checklist

For visual work, enumerate every visible element from the approved design/demo. Use
one row per element and mark `MATCH` only after comparing the rendered application
screenshot with the approved reference. Link the screenshot or PR/issue attachment
in Evidence. Omit this section only when Visual review is Not applicable.

| Element | Expected | Result | Evidence |
|---|---|---|---|
| `<header, rail, control, or state>` | `<approved design description>` | MATCH | `<screenshot link>` |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | `<test, screenshot, or report link>` | |

## Unresolved findings

- None
