# ADR-0265: MFA secrets are encrypted at rest under a dedicated vault key

**Date:** 2026-09-03
**Status:** Accepted
**Context:** #3591. Item 13 of the spec's decisions, added after initial approval
as a security fold-in and ruled by Tehom in session on 2026-09-03.

## Decision

`Authenticator.data` (the TOTP secret and the recovery-code seed) is encrypted
at rest under a dedicated key, `MFA_SECRETS_KEY`, separate from Django's
`SECRET_KEY`. `ArxMFAAdapter` (`src/evennia_extensions/mfa_adapter.py`,
`MFA_ADAPTER`) implements `encrypt`/`decrypt` with `cryptography.fernet
.MultiFernet` over a comma-separated list of Fernet keys read from
`MFA_SECRETS_KEY`, first key current: `MultiFernet` always encrypts with the
first key and decrypts with any configured key, so rotation is prepend the new
key, deploy, re-encrypt every row, drop the old key, deploy again, never a hard
cut that locks out rows written under the key being retired.

A Django system check (`evennia_extensions.checks.check_mfa_secrets_key`,
`evennia_extensions.E001`) builds a `Fernet` for every configured key at
`migrate`/`check` time, failing the converge before a release with a bad key
goes live. A REQUIRED-tier sentinel probe (`mfa-secrets-key` in
`web/admin/tuning/required_content.py`) additionally decrypts the oldest
stored TOTP row on demand, so a key that parses but no longer decrypts real
data (the wrong key deployed, or a rotation that skipped re-encryption) is
visible to staff before a player's sign-in fails on it. A decrypt failure
raises loudly (`ValueError` naming `MFA_SECRETS_KEY`) rather than silently
rejecting a code.

## Why

allauth's default `DefaultMFAAdapter.encrypt`/`decrypt` are the identity
function: TOTP secrets and recovery-code seeds are stored in the clear in
`Authenticator.data`, a `JSONField`. Production backups are `pg_dump` piped
through gzip and shipped to object storage with no client-side encryption, so
under the default, a leaked backup or a leaked database credential would hand
out every enrolled player's second factor at once, forcing mass re-enrolment
and a breach notification. Encrypting at the application layer under a key
that never touches the backup path closes that specific gap without changing
how backups are taken. The key is deliberately not `SECRET_KEY` so Django's
key can still be rotated on its own schedule (that key only signs sessions and
similar short-lived tokens) without touching 2FA at all, and so that a
`SECRET_KEY` leak and an `MFA_SECRETS_KEY` leak stay two separate incidents
with two separate blast radii.

## Rejected

- **allauth's plaintext default.** Leaves the exact backup-leak exposure
  described above; not acceptable now that account settings makes 2FA a
  first-class, encouraged feature rather than an unused, dormant one.
- **Reusing `SECRET_KEY` as the encryption key.** Couples an operational key
  that legitimately gets rotated for unrelated reasons (session signing) to a
  key whose rotation is expensive (every stored secret must be re-encrypted or
  it becomes unreadable), and means a `SECRET_KEY` leak is also a full 2FA
  compromise. A dedicated key keeps the two rotation schedules and the two
  leak scenarios independent.
