# Registration gates on per-email invites, not codes or an allowlist, behind a DB-singleton open/closed toggle

Alpha runs on the production deploy with no closed-registration mechanism anywhere in
the stack — the box being reachable meant anyone could self-register via allauth
headless signup. We chose staff-issued, per-email single-use `AccountInvite` rows
over redeemable codes (not email-bound, so a link could be shared beyond the invited
person) or a plain allowlist table (no issuance audit trail): email binding gives
auditability ("who let this person in") and matches the closed-list reality of
alpha. The open/closed switch is a DB-singleton config row
(`RegistrationConfig`, mirroring `SceneRoundDefaultsConfig`), staff-editable via
admin, not an env var — cutover to early-access open registration is meant to be an
operational act, not a deploy.

> Status: accepted · Source: issue #3054
