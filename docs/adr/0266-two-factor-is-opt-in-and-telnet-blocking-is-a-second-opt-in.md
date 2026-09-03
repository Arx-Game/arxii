# ADR-0266: Two-factor authentication is opt-in and telnet blocking is a second opt-in

**Date:** 2026-09-03
**Status:** Accepted
**Context:** #3591. Account settings gives players two-factor authentication (2FA)
via `allauth.mfa` (TOTP plus recovery codes). Item 5 of the spec's decisions was
flagged for a human ruling; Tehom ruled on 2026-09-03.

## Decision

2FA is opt-in per account and never required. No setting, staff flag, or role
forces enrolment, and nothing in the site nags a player toward it beyond the
2FA card itself.

Evennia's telnet login authenticates by password alone and cannot prompt for a
second factor, so enrolling in 2FA changes nothing about telnet by itself. A
player who wants their second factor to actually gate every sign-in path can
additionally switch on a second, separate opt-in, `PlayerData
.block_telnet_login_with_2fa` (default `False`, written only through
`GET`/`PATCH /api/account/security-settings/`). Only when that flag is on and
the account has 2FA enrolled does `Account.authenticate`
(`src/typeclasses/accounts.py`) refuse a password-correct telnet sign-in, with
a message pointing the player at the web client. The refusal is checked after
the parent authenticate has already matched the password, so a wrong password
gets the same answer whether or not the flag is set, and the flag is never an
oracle for whether 2FA is enrolled. Turning 2FA off leaves the flag stored but
inert. The React web client authenticates by Django session and the game
socket does too, so neither passes through this method; only telnet and the
raw websocket connect command are affected.

## Why

The alternative that automatically blocks telnet the moment 2FA is enrolled
would silently strand any player who uses telnet as a secondary client the
moment they turn on 2FA for the web, with no chance to reconsider. A second,
explicit switch keeps the two decisions ("protect my account with a second
factor" and "refuse a client that cannot check a second factor") separate and
reversible independently, and it means enrolling in 2FA is never a trap.

## Rejected

- **Blocking telnet automatically once 2FA is enrolled.** Removes the choice
  the decision above is built to preserve, and a player who wanted 2FA on the
  web only would lose telnet access with no warning.
- **Making 2FA required for anyone (all players, staff, or GMs).** Two-factor
  authentication protects an account its owner chooses to protect; making it
  mandatory for any cohort would gate play behind a security feature the
  design goal explicitly keeps optional, and would create a new class of
  lockout (a required authenticator app) with no opt-out.
