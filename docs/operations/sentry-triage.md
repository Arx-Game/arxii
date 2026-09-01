# Sentry triage — getting production errors onto the board

Sentry ingest has been live since #2236 Phase 5, but the errors were write-only: the
`SENTRY_DSN` in `src/server/conf/settings.py` can send events and read nothing back. This
is the read side.

## The loop

1. **`.github/workflows/sentry-digest.yml`** runs `tools/sentry_digest.py` daily at
   09:00 UTC (and on `workflow_dispatch`, with a `dry_run` input).
2. The tool fetches unresolved issues for the project and rewrites **one rolling GitHub
   issue** labelled `sentry` — the digest. If a digest is already open it is edited in
   place, so the board carries exactly one card no matter how many errors are live.
3. **If Sentry is clean, no issue is created**, and an open digest is closed with a
   comment. A standing "0 issues" card would only teach people to ignore the label.
4. An agent picks a row, opens it *in Sentry*, fixes it on a branch, and ships a PR.
5. Once merged, `python tools/sentry_resolve.py ARX2-6` marks it resolved in Sentry.
   Close the digest when every row is handled; the next run opens a fresh one if
   anything is still unresolved.

## Closing an issue with rigor

Bugs here get fixed without anyone touching Sentry, so unresolved issues accumulate
that are already dead. Clearing them is right, but "it looks old" is not a reason. The
test is whether the fix is **in the build production is actually running**, and the
answer is checkable, because every event is tagged with `release` = the deployed commit
SHA (`SENTRY_RELEASE`, stamped by `app_deploy` at checkout).

```bash
# 1. the SHA production was running when the error last fired
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/issues/<numeric-id>/events/" |
  python -c "import json,sys;[print(e['dateCreated'],{t['key']:t['value'] for t in e['tags']}.get('release')) for e in json.load(sys.stdin)]"

# 2. the commit that fixed it
git log -S '<the broken expression>' -- <path/to/file.py>

# 3. is the fix in that build?
git merge-base --is-ancestor <fix-sha> <deployed-sha> && echo IN || echo NOT-IN
```

Then pick the status from what you found:

| What you established | Status | Why |
| --- | --- | --- |
| Fix is in the deployed build, no events since | `resolved` | Genuinely gone in production |
| Fix is merged to main but **not** deployed | `resolvedInNextRelease` | Sentry reopens it if it recurs after the next release |
| No fix identified | leave it open, or fix it | An old date is not a diagnosis |

**The trap this guards:** merging to `main` does not deploy. Releases here are
tag-triggered (`v1.2.3-release`), so main can be days ahead of production — on
2026-09-01 the deployed build was nine days behind, and an issue whose fix had already
merged was still firing in prod. `resolvedInNextRelease` is the honest status for that
state; plain `resolved` would have claimed something untrue and lost the regression
signal.

Either status keeps the safety net: if the error happens again, Sentry reopens the issue
and the next digest lists it. That is what makes closing safe rather than tidy.

## The digest deliberately withholds the error

Each row is a short id, a link, the level, event/user counts and first/last-seen dates —
and nothing else. **No message, no culprit path, no stack frames, no request data.** This
repo is public, and a quoted production traceback is a reproduction recipe for a failure
in a live game. The detail lives behind Sentry's auth; the digest only points at it. See
[ADR-0254](../adr/0254-sentry-digest-is-a-pointer-not-a-reproduction.md), and
`test_body_never_leaks_message_or_culprit`, which fails if anything richer creeps into
the body.

The practical cost: you cannot triage from the GitHub issue alone. Working a Sentry row
requires Sentry access. That is the trade, taken on purpose.

## Credentials

`SENTRY_AUTH_TOKEN` needs `org:read`, `project:read`, `event:read` and `event:write`
(the last is what `sentry_resolve.py` needs). It is a different credential from the
ingest DSN, which can only write.

**Not an Organization Auth Token.** The tokens under
`https://sentry.io/settings/arx2/auth-tokens/` (they start `sntrys_`) are
release-management credentials for sentry-cli — their scopes are fixed, not editable,
and they 403 on every issue-read endpoint. Verified 2026-09-01: one returned 403 even
on `GET /organizations/arx2/`. Use one of these instead:

- **Internal Integration (preferred).** Settings -> Developer Settings -> New Internal
  Integration; set Permissions -> *Issue & Event: Read & Write*, then copy the generated
  token. It belongs to the org rather than a person, so it survives anyone leaving, and
  its permissions genuinely are selectable.
- **User Auth Token.** Settings -> Account -> API -> Auth Tokens
  (`https://sentry.io/settings/account/api/auth-tokens/`), ticking the four scopes above.
  Quicker, but it is tied to one person's account.

Once minted, store it in both places:

- **CI:** `gh secret set SENTRY_AUTH_TOKEN --repo Arx-Game/arxii`. The workflow step is
  guarded by `if: env.SENTRY_AUTH_TOKEN != ''`, so before the secret exists the job skips
  rather than going red every morning.
- **Locally:** export it in your shell, or add it to `src/.env`. It is never committed.

The org slug and numeric project id are constants in `tools/sentry_constants.py`; the
project id is the `?project=` value from any Sentry issue-stream URL.

## Commands

```bash
python tools/sentry_digest.py --dry-run     # print the digest, touch no issue
python tools/sentry_digest.py               # create or update the rolling digest
python tools/sentry_resolve.py ARX2-6     # resolve one (accepts several, or numeric ids)
python tools/sentry_resolve.py ARX2-6 --status ignored
```
