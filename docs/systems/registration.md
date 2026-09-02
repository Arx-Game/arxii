# Registration System

Invitation-gated account registration (#3054). Registration is closed by default: a
visitor can read the public site but cannot self-register unless staff open
registration globally or issue them a per-email single-use invite. This is a real
feature, not a throwaway alpha gate — alpha doubles as its live test, and the same
gate stays useful for early access (staff flip one DB-backed toggle to open it, no
deploy required).

**Source:** `src/world/registration/`
**API prefix:** `/api/registration/` (public status) + `/api/staff/` (staff invite
management)
**Adapter seam:** `evennia_extensions.adapters.ArxAccountAdapter`

---

## Enums

```python
# InviteStatus (TextChoices) — in world.registration.constants; derived, never stored:
# PENDING   - Not redeemed, not revoked, not expired
# REDEEMED  - AccountInvite.redeemed_at is set
# REVOKED   - AccountInvite.revoked_at is set
# EXPIRED   - now() >= AccountInvite.expires_at
```

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `RegistrationConfig` | Singleton (pk=1) staff-tunable open/closed toggle — mirrors `world.scenes.models.SceneRoundDefaultsConfig` | `registration_open` (bool, default False), `updated_at`, `updated_by` |
| `AccountInvite` | Staff-issued, per-email single-use invitation | `email`, `token` (unique, `secrets.token_urlsafe(32)`), `invited_by` (AccountDB, PROTECT), `created_at`, `expires_at` (default 30 days), `redeemed_at`/`redeemed_by`, `revoked_at`, `note` |
| `AccountMailFailure` | Ledger of failed account-mail sends (#3193) — written by `ArxAccountAdapter.send_mail`'s catch, read-only in admin | `email`, `template_prefix`, `error`, `created_at` |

`AccountInvite` is email-bound rather than a bare redeemable code: an issued invite
is auditable ("who let this person in") and can't be shared beyond the invited
address. Its `status` property derives `InviteStatus` from the three timestamp
columns — never stored redundantly. `is_redeemable` is `True` only when none of
`is_redeemed`/`is_revoked`/`is_expired` hold.

**Two invite systems, one gate (#3182).** `world.roster.GameInvite` (#2483,
player-issued invite-a-friend, trust-gated, no email binding) shares the
`/register?invite=TOKEN` URL but does **not** open signup:
`ArxAccountAdapter.is_open_for_signup` consults `AccountInvite` only. While
`registration_open` is False the invite-a-friend feature is off entirely —
`create_game_invite` and `claim_game_invite` raise
`world.roster.services.invite_services.RegistrationClosedError` and
`resolve_invite` returns None — so a player invite can never side-door the
staff gate. When registration is open, `GameInvite` adds context (inviter
message, application annotation) on top of open signup.

---

## Service functions (`world.registration.services`)

- `issue_invite(email, invited_by, note="") -> AccountInvite` — active-invite dedup:
  an email with an existing redeemable invite gets that same row back, not a
  duplicate; an email with only dead (redeemed/revoked/expired) invites gets a
  fresh row. **Emails the redemption link on both branches**, because "invite this
  person" means the same thing to staff either way, and re-issuing is the natural
  way to say "send it again".
- `send_invite_email(invite) -> bool` — mails the redemption link to the address the
  invite is bound to. Returns False and logs instead of raising: the row is already
  committed and still valid, and the staff page keeps Copy Link as the manual
  fallback for a bounced send. Only call it for a redeemable invite.
- `revoke_invite(invite, by) -> AccountInvite` — stamps `revoked_at`.
- `signup_allowed(email, token) -> bool` — the pure predicate the adapter calls;
  never distinguishes *why* a token fails (leak-analysis: no oracle for probing
  which emails hold invites — no invite, wrong email, expired, and revoked all
  collapse to `False`).
- `redeem_invite(token, email, account) -> AccountInvite | None` — validates
  binding + state, stamps `redeemed_at`/`redeemed_by`; called from the adapter's
  `save_user` immediately after account creation. `None` on any mismatch (a
  concurrent redeem, since expired/revoked, etc.) — the signup itself has already
  happened by then, gated separately by `is_open_for_signup`.
- `record_mail_failure(email, template_prefix, error) -> AccountMailFailure` —
  persists a failed account-mail send (#3193); called from the adapter's
  `send_mail` catch so a silent mail outage shows up in the admin.
- `build_verification_link(email) -> str` — the staff fallback when mail cannot
  reach a player (#3193): resolves the (unverified) allauth `EmailAddress`,
  generates an `EmailConfirmationHMAC` key on demand (no DB row, time-bounded by
  `ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS`), and formats it into
  `HEADLESS_FRONTEND_URLS["account_confirm_email"]`. Raises
  `EmailAddress.DoesNotExist` / `AlreadyVerifiedError`.

`get_registration_config()` (in `models.py`) mirrors
`get_scene_round_defaults_config()` — `cached_singleton()` first, `get_or_create`
fallback, closed by default.

---

## The adapter seam

`ArxAccountAdapter.new_user(request)` returns an instance of
`settings.BASE_ACCOUNT_TYPECLASS`, never allauth's default `get_user_model()()`.
Evennia pins `db_typeclass_path` to the class an instance was built as, so a bare
`AccountDB` stays bare on every later load and lacks the whole `Account` typeclass
(`puppet`, `get_available_characters`, the persona cache); every web-signup player
was in that state until Sentry ARX2-8 (2026-09-02). Migration
`0213_account_typeclass_backfill` repoints existing rows, and the ops dashboard's
required-content panel flags any new one (`typeclassed-accounts`; Django's
`createsuperuser` still produces them). See ADR-0260.

`ArxAccountAdapter.is_open_for_signup(request)` (`src/evennia_extensions/adapters.py`)
is the allauth hook this gate hangs on. It was previously unoverridden — the
standard hook allauth's headless `SignupView.post` already calls before doing
anything else:

```python
def post(self, request, *args, **kwargs):
    if request.user.is_authenticated:
        return ConflictResponse(request)
    if not get_account_adapter().is_open_for_signup(request):
        return ForbiddenResponse(request)   # <- neutral 403, same for every failure mode
    ...
```

**Seam decision (why `request.body`, not the validated `SignupInput`):** by the time
`post()` runs, `RESTView.handle()` has already JSON-decoded the POST body once (to
validate the `SignupInput` form) — but `is_open_for_signup(request)` only receives
`request`, not that parsed input. Django's `HttpRequest.body` is a cached property
(read once, stashed on `request._body`); re-reading it inside the adapter is a free
re-read of the same bytes, not a second consumption of the request stream. The
adapter re-parses the JSON body itself (`_invite_fields_from_request`) to read
`email`/`invite_token`. Proven against the real endpoint (not just the adapter in
isolation) by `world/registration/tests/test_signup_journey.py`, which posts to
`/api/auth/browser/v1/auth/signup` exactly as the React signup form does.

`save_user` additionally calls `redeem_invite` when a token was posted, stamping
redemption in the same request that created the account.

**Mail is best-effort at this seam (#3193).** `ArxAccountAdapter.send_mail`
wraps allauth's send in a broad catch: the account row and invite redemption
commit *before* the verification send runs, so a mail-provider failure
(SMTP timeout, Resend API error, broken template) must not turn a successful
signup — or a login, via `send_verification_email_at_login` — into a 500. The
failure is logged and recorded as an `AccountMailFailure` row; the next login
retries the send, and staff can hand over a verification link directly (below).

---

## API

| Endpoint | Method | Access | Purpose |
|---|---|---|---|
| `/api/registration/status/` | GET | Public | `{"open": bool}` — never enumerates invites |
| `/api/staff/invites/` | GET, POST | Staff (`IsAuthenticated` + `IsAdminUser`) | List (filterable by `email`, `status`) / issue |
| `/api/staff/invites/{id}/` | GET | Staff | Retrieve one invite |
| `/api/staff/invites/{id}/revoke/` | POST | Staff | Revoke an un-redeemed invite |
| `/api/staff/invites/{id}/resend/` | POST | Staff | Email the redemption link again. 400 if the invite is not redeemable (a redeemed, revoked or expired invite has no working link to send); 502 if the send itself fails, so staff know to fall back to Copy Link |
| `/api/staff/verification-link/` | POST | Staff | `{email}` → `{email, link}` — the email-verification URL for an unverified account (#3193). 404 unknown address, 400 already verified. Generation is audit-logged |
| `/api/auth/browser/v1/auth/signup` | POST | Public (gated) | allauth headless signup — the frontend posts `{username, email, password, invite_token?}` here; `invite_token` is omitted entirely when the signup form's Invite Code field is empty |

---

## Frontend

- `frontend/src/evennia_replacements/RegisterPage.tsx` — reads `?invite=` from the
  URL into an editable "Invite Code" field (`react-hook-form` default value);
  fetches `useRegistrationStatus()` and renders an invite-only notice instead of
  the form only on an explicit `open: false` with no invite param present (never
  while the status fetch is still loading — a slow/failed check doesn't block
  signup).
- `frontend/src/staff/pages/StaffInvitesPage.tsx` (routed at `/staff/invites`,
  linked from the Staff Hub) — issue form (email + optional note), status-filter
  tabs, per-invite resend-email/copy-link/revoke actions. Mirrors
  `StaffApplicationsPage`'s list/filter shape. Copy Link is kept alongside Resend
  Email deliberately: it is the fallback when a send bounces or the address is
  wrong, and it does not depend on outbound mail working. The page also carries
  the Copy Verification Link form (#3193): staff enter an account's email and
  get its verification URL on the clipboard — the post-signup sibling of the
  invite Copy Link fallback.
- The login/signup error paths in `frontend/src/evennia_replacements/api.ts`
  parse error bodies with `res.json().catch(() => null)` and give 5xx responses
  honest messages (#3193) — Django's HTML 500 page must never surface as a raw
  `Unexpected token '<'` parser error.

---

## Email delivery

`world.registration.email_service.RegistrationEmailService` subclasses
`EmailServiceBase` from `world.roster.email_service` rather than adding a parallel
sending helper — that base exists so sibling domain services can share
`_send_email` without inheriting roster's domain-specific signatures (#2162). The
template is `world/templates/registration/email/account_invite.html`, matching the
roster email templates' shape.

The link is built server-side from `settings.SITE_URL`
(`{SITE_URL}/register?invite={token}`), not from a request origin. The staff page's
own `inviteLink()` helper builds the same URL from `window.location.origin`, which
is correct in the browser but unavailable when sending mail.

Delivery rides the existing Resend HTTPS API backend: `settings.py` switches
`EMAIL_BACKEND` to `world.roster.email_backend.ResendAPIEmailBackend` whenever
`RESEND_API_KEY` is present and `DEBUG` is off, which is the same path allauth's
verification and password-reset mail already uses. No separate mail configuration
exists for invites. See ADR-0216 for why this is an HTTPS API call and not SMTP.

---

## Settings

- `NEW_ACCOUNT_REGISTRATION_ENABLED = False` (`src/server/conf/settings.py`) closes
  Evennia's telnet `create` command — the only other account-creation door besides
  the web signup form, which the adapter gates separately.
- The telnet connect screen (`src/server/conf/connection_screens.py`) points a
  telnet-only visitor at the website and reminds a newly-created account to run
  `account email <address>` to satisfy the mandatory email-verification gate.

---

## Adjacent: manual email-verify fallback

Already built, not part of this feature: `EmailAddressAdmin`
(`src/evennia_extensions/admin.py`) registers `mark_as_verified` /
`mark_as_unverified` / `resend_verification_email` admin actions on allauth's
`EmailAddress` model — the staff fallback for a Resend misdelivery. Verified present
via `admin.site._registry` before building anything new for it (#3054
anti-reinvention pass).

---

## Testing

- `world/registration/tests/test_models.py` — singleton accessor, `AccountInvite`
  status derivation.
- `world/registration/tests/test_services.py` — issue dedup/fresh-row, revoke,
  `signup_allowed`, `redeem_invite`.
- `world/registration/tests/test_adapter.py` — `is_open_for_signup` unit tests via
  `RequestFactory` with a raw JSON body.
- `world/registration/tests/test_signup_journey.py` — journey tests at the real
  headless signup endpoint (closed+no-invite, valid invite+matching email, wrong
  email, open, reused invite, expired/revoked with the same neutral response).
- `world/registration/tests/test_api.py` — `RegistrationStatusView` +
  `AccountInviteViewSet` permission (staff/player/anonymous) and issue/list/revoke
  journeys.
