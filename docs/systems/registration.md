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
**Adapter seam:** `evennia_extensions.adapters.ArxAccountAdapter` (`is_open_for_signup`
for the invite gate, `get_client_ip` for rate-limit key hardening, #3591)

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
Evennia pins `db_typeclass_path` to the class an instance was built as, so the row says
`evennia.accounts.models.AccountDB` (the base model, not `typeclasses.accounts.Account`),
loads as that on every later load, and lacks the whole `Account` typeclass
(`puppet`, `get_available_characters`, the persona cache). That was Sentry ARX2-8
(2026-09-02): the first outside player's account, made by signup, 500'd on every
events list. The signup journey test proves the row shape end to end. Rows from
before the fix, and
any Django `createsuperuser` makes, are repointed by hand; the ops dashboard's
required-content panel names them (`typeclassed-accounts`). No data migration: a
handful of pre-launch rows is a shell one-liner, not schema history. See ADR-0260.

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

## Account settings (#3591)

A signed-in player manages email, password, and two-factor authentication (2FA) at
`/profile/account`. Every state change goes through `allauth.headless` endpoints
already mounted at `/api/auth/` (`path("auth/", include("allauth.headless.urls"))`
in `src/web/api/urls.py`); there are no home-grown
credential views. See ADR-0266 (telnet's opt-in 2FA block) and ADR-0267 (secrets
encrypted at rest).

### Endpoints

All headless routes are under `/api/auth/browser/v1/`.

| Goal | Method + path | Notes |
|---|---|---|
| Read addresses | `GET account/email` | At most one pending address alongside the current one |
| Change email | `POST account/email {email}` | Adds a pending address, sends verification mail |
| Resend / cancel pending | `PUT account/email {email}` / `DELETE account/email {email}` | |
| Change password | `POST account/password/change {current_password, new_password}` | Session stays authenticated |
| Reauthenticate (password) | `POST auth/reauthenticate {password}` | Under `auth/`, not `account/` |
| Reauthenticate (2FA code) | `POST auth/2fa/reauthenticate {code}` | Under `auth/`, not `account/` |
| 2FA status | `GET account/authenticators` | |
| Start TOTP enrolment | `GET account/authenticators/totp` | 404 envelope carries `meta.secret` and `meta.totp_url` when not yet enrolled |
| Confirm TOTP | `POST account/authenticators/totp {code}` | Also generates recovery codes |
| Disable TOTP | `DELETE account/authenticators/totp` | |
| Recovery codes | `GET` / `POST account/authenticators/recovery-codes` | GET shows unused codes, POST regenerates |
| Login second factor | `POST auth/2fa/authenticate {code}` | After `auth/login` answers 401 with a pending `mfa_authenticate` flow |

| Goal | Method + path | Notes |
|---|---|---|
| Telnet-block flag | `GET` / `PATCH /api/account/security-settings/` | `IsAuthenticated`; reads and writes `request.user.player_data` only. Anonymous gets 403 (DRF `SessionAuthentication`, not 401) |

### Settings

`src/server/conf/settings.py`:

- `ACCOUNT_CHANGE_EMAIL = True` - single email per account; a change is a pending
  second address, promoted on verification.
- `ACCOUNT_REAUTHENTICATION_REQUIRED = True` - the email flows raise the reauth
  challenge only when this is on; the MFA flows raise it unconditionally either
  way.
- `ACCOUNT_EMAIL_NOTIFICATIONS = True` - allauth mails "password changed" /
  "email changed" through `ArxAccountAdapter.send_mail`, already best-effort
  (#3193).
- `MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]` - WebAuthn is left out.
- `MFA_TOTP_TOLERANCE = 1` - accepts the previous and next 30-second step, for
  clock drift.
- `MFA_ALLOW_UNVERIFIED_EMAIL = True` - lifts allauth's interlock between a
  pending email change and 2FA enrolment (operational risk 3, below); mandatory
  verification before login and the reauthentication gate on email changes keep
  the property allauth's interlock was protecting.
- `MFA_TOTP_ISSUER = "Arx II"` - the label shown in an authenticator app.
- `MFA_ADAPTER = "evennia_extensions.mfa_adapter.ArxMFAAdapter"` - see below.
- `MFA_SECRETS_KEY = env("MFA_SECRETS_KEY")` - required, like `SECRET_KEY`;
  comma-separated Fernet keys, first key current.
- `LOGIN_URL = "/login"` - the React login page; allauth's `secure_admin_login`
  redirects here.

`INSTALLED_APPS` gains `allauth.mfa`. `pyproject.toml` depends on
`django-allauth[mfa]` (adds `fido2` and `qrcode`): without the extra, importing
`allauth.mfa` crashes at startup even when WebAuthn is never used, because
`mfa/stages.py` imports the WebAuthn module unconditionally.

**Dev quirk:** the `arx` CLI loads `src/.env` with override, so a shell-exported
`MFA_SECRETS_KEY` is masked in dev by whatever `src/.env` holds. Prod reads the
systemd `EnvironmentFile` instead, so this only bites local development.

### Telnet and 2FA

2FA is opt-in and never required, and enrolling in it changes nothing about
telnet on its own; Evennia's telnet login authenticates by password alone and
cannot prompt for a second factor. A player who wants their second factor to
actually gate sign-in can additionally switch on
`PlayerData.block_telnet_login_with_2fa` (default `False`, written only through
`/api/account/security-settings/`); only when that flag is on *and* the account
has 2FA enrolled does telnet password sign-in get refused, with the account's
password still checked first so a wrong password gets the same answer as
today. The refusal message is: "This account refuses telnet sign-in while
two-factor authentication is on. Sign in through the web client." Enforced in
`Account.authenticate` (`src/typeclasses/accounts.py`), which calls
`super().authenticate(...)` first and only substitutes the refusal after the
parent has already matched the password; the React web client and the game
socket authenticate by Django session and never pass through this method.

### Admin

The Django admin signs in through the web login rather than its own
password-only form: `ArxAdminSite.login` (`src/web/admin/__init__.py`) wraps
Django's stock `AdminSite.login` with allauth's `secure_admin_login`, which
sends an unauthenticated visitor to `LOGIN_URL` with `?next=` instead of
rendering `/admin/login/` directly; `ArxAdminSite.admin_view` carries the same
redirect for every other staff page so an unauthenticated hit collapses to one
path instead of two. `LoginPage` honours a same-origin relative `next` after a
successful sign-in, so a 2FA-enrolled staff account reaches the admin only
after clearing 2FA the normal way. A staff member already signed in on the
site reaches the admin as before.

allauth's stock `AuthenticatorAdmin` renders `Authenticator.data` (the TOTP
secret and recovery-code seed) on the change form to anyone with admin access.
It is re-registered (`src/evennia_extensions/admin.py`) with `data` excluded
and `user`, `type`, `created_at`, `last_used_at` the only visible fields, no
add and no change permission, so the only action available is delete, which is
the lockout reset below.

### Runbooks

**(a) Player lockout reset.** Staff verify identity out of band, then in the
Django admin go to MFA > Authenticators, delete the account's rows, and tell
the player. Deleting the TOTP row also removes its dangling recovery codes.
With no authenticator left, `PlayerData.block_telnet_login_with_2fa` (if the
player had set it) goes inert, and telnet sign-in works again. No shell, no
database access needed.

**(b) Administrator lockout**, layered cheapest first:

- Enrolment hygiene: recovery codes go in a password manager, and the same QR
  is scanned by two devices at setup.
- Two-person rule: any two staff with admin rights can reset each other in the
  admin, using the runbook above.
- Standing break-glass account: the first-run superuser the converge creates
  never enrols in 2FA and is used for nothing but resets; its password is held
  only as the `ARXII_DJANGO_SUPERUSER_PASSWORD` Environment secret.
- Break-glass without any admin login: a `workflow_dispatch` input that deletes
  a named account's `Authenticator` rows through the converge's existing
  `python -m django shell` step, gated by the `prod` Environment, so an org
  member could recover with only their GitHub sign-in, audit-logged in
  Actions. Proposed, not built.

**(c) Key rotation.** Prepend the new key to `ARXII_MFA_SECRETS_KEY` (so it
becomes the leading, current key) and deploy. Then, in `arx manage shell`:

```python
from allauth.mfa.models import Authenticator
from evennia_extensions.mfa_adapter import ArxMFAAdapter

a = ArxMFAAdapter()
for row in Authenticator.objects.all():
    for field in ("secret", "seed"):
        if field in row.data:
            row.data[field] = a.encrypt(a.decrypt(row.data[field]))
    if "migrated_codes" in row.data:
        row.data["migrated_codes"] = [a.encrypt(a.decrypt(c)) for c in row.data["migrated_codes"]]
    row.save(update_fields=["data"])
```

`migrated_codes` is allauth's imported-recovery-codes path
(`allauth/mfa/recovery_codes/internal/auth.py`); nothing in this app writes it
today, but the loop covers it so a future write is never stranded unencrypted
mid-rotation.

Drop the old key from `ARXII_MFA_SECRETS_KEY` and deploy again. `MultiFernet`
encrypts with the first (current) key and decrypts with any configured key,
which is what makes prepend-then-re-encrypt-then-drop safe: nothing is ever
unreadable mid-rotation.

**(d) Clock drift.** Every stored code failing at once, for every player, is
the symptom of server clock drift: TOTP is pure time arithmetic and
`MFA_TOTP_TOLERANCE = 1` only covers plus or minus one 30-second step. Check
with `timedatectl` (look for `System clock synchronized: yes` and
`NTP service: active`); the base Ansible role asserts `systemd-timesyncd` is
enabled and active for this reason. If drift has already happened, resetting
the affected accounts' authenticators (runbook a) is the immediate fix; the
underlying clock issue is separate.

### Operational risks

Researched 2026-09-03 against allauth 65.14.1 and the prod infra in
`infra/ansible`.

| # | Risk | Mitigation |
|---|---|---|
| 1 | `allauth.mfa` imports `fido2` at module load even when WebAuthn is unused; missing the extra takes the whole site down at import time, not just 2FA. | `django-allauth[mfa]` in `pyproject.toml`, plus an import smoke test. |
| 2 | Server clock drift fails every stored TOTP code at once (zero default tolerance). | `MFA_TOTP_TOLERANCE = 1`; a base-role task asserting `systemd-timesyncd` is enabled and active; runbook (d) above. |
| 3 | allauth's stock interlock blocks email changes and 2FA enrolment from each other, meant to stop an attacker signing up, never verifying, and locking out the real owner. | `MFA_ALLOW_UNVERIFIED_EMAIL = True` lifts it; mandatory verification before login and the reauthentication gate on email changes preserve the property it protected. The 2FA card also hides "Set up" until the email is verified. |
| 4 | allauth's per-IP rate limits read the first `X-Forwarded-For` entry, which a client can forge. | `ArxAccountAdapter.get_client_ip` prefers `X-Real-IP`, which Caddy sets from Cloudflare's `CF-Connecting-IP` and a client cannot forge. |
| 5 | allauth's default `Authenticator.data` storage is plaintext; backups (`pg_dump` piped to gzip and shipped to object storage) carry no client-side encryption. | `ArxMFAAdapter` encrypts under `MFA_SECRETS_KEY` (ADR-0267); losing that key is the new failure mode, mitigated by the vault placement, the system check, and the `mfa-secrets-key` sentinel probe. |
| 6 | A player, or an administrator, loses their phone and recovery codes. | Runbooks (a) and (b) above. |
| 7 | Used-code replay protection lives in Django's in-process cache, correct only for a single server process. | Noted; not acted on, since Evennia runs as one process. Revisit if Django is ever split across processes. |
| 8 | The pending TOTP secret between setup and confirmation lives in the session. | Sessions are database-backed, so a reload mid-enrolment is safe; a player who logs out mid-enrolment simply starts over. |
| 9 | An account with no usable password and no 2FA gets no reauthentication challenge (allauth's own documented gap). | Accepted; such an account can still enrol 2FA, after which the 2FA reauth challenge applies. |
| 10 | The migration is additive (three `allauth.mfa` migrations creating one table, `Authenticator`, whose `type` column holds TOTP, recovery-codes, and WebAuthn rows alike, plus one first-party boolean with a default). | `migrate --noinput` on converge cannot lose or block anything; ADR-0237's data-disposition rule does not apply. |
| 11 | Django's stock `AdminSite.login` never runs allauth's MFA stage, so a 2FA-enrolled staff account could sign into `/admin/login/` on its password alone. | `ArxAdminSite.login` wrapped with `secure_admin_login` (Admin, above). |
| 12 | allauth's stock admin shows `Authenticator.data` (the secret, in the clear) to any staff member with admin access. | Read-only `AuthenticatorAdmin` with `data` excluded (Admin, above); with ADR-0267 the column is ciphertext regardless. |
| 13 | `pull-prod` copies encrypted secrets into a dev database, which cannot decrypt them without the prod key. | Harmless: the sentinel probe reports the mismatch. Never copy the prod `ARXII_MFA_SECRETS_KEY` into a dev `.env`. |

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
- `world/registration/tests/test_adapter.py` also carries `ClientIpTests`
  (#3591): `get_client_ip` prefers `X-Real-IP` and ignores a forged
  `X-Forwarded-For`.

**Account settings (#3591):**

- `web/api/tests/test_account_settings_journey.py` - password change, email
  change through the custom verify view, reauthentication challenge and retry,
  TOTP enrol, login second factor, recovery-code sign-in, and disable, all at
  the real headless endpoints through `APIClient`.
- `web/api/tests/test_account_security_settings.py` - `GET`/`PATCH`
  `/api/account/security-settings/`, default value, anonymous 403.
- `web/api/tests/test_mfa_wiring.py` - the `fido2` dependency-guard import
  smoke test, the headless MFA routes resolving, and the settings block.
- `evennia_extensions/tests/test_mfa_adapter.py` - `ArxMFAAdapter` encrypt and
  decrypt round-trip, a second key prepended to `MFA_SECRETS_KEY` still
  decrypting rows written under the first, a wrong key raising instead of
  silently rejecting a code.
- `typeclasses/tests/test_account_authenticate_2fa.py` - `Account.authenticate`
  returns the normal account when the flag is off, refuses telnet only when
  both the flag and 2FA are on, and restores telnet when 2FA is turned off with
  the flag still stored; the guard is proven by first watching it fail without
  the override.
- `web/admin/tests/test_admin_login_2fa.py` - an unauthenticated `GET /admin/`
  redirects to `/login?next=/admin/`, a 2FA-enrolled staff account posting
  password-only to `/admin/login/` is not logged in, and the Authenticator
  change form has no `data` field.
