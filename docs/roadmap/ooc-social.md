# OOC Social & Community

**Status:** in-progress
**Depends on:** Scenes, Relationships

## Overview
The out-of-character social infrastructure that keeps the game community healthy and fun. MUSHes are made of creatives with big personalities — clashes are common. Systems here reward positive behavior, make it easy to find friends and RP, and provide escape valves when things get tense.

## Key Design Points
- **Kudos system:** Rewards for positive OOC behavior — helping players, mentoring, recruiting, being a good community member. Players recognize each other for making the game better
- **Friend tracking:** Easy tracking of who among other players are friends, with quick access to find them on grid
- **Visibility controls:** Players can hide OOC visibility so they aren't swarmed when logging in. Prevents the overwhelming "everyone wants my attention" feeling that drives people to log off
- **Easy opt-in/opt-out:** All social connections are easy to establish and easy to dissolve. No pressure mechanics
- **Consent groups:** OOC visibility groups for player-controlled content sharing — decide who can see what about your character and activity
- **Finding RP:** Making it trivially easy to find active scenes, available players, and slip into RP. The game should feel alive and accessible the moment you log in
- **Anti-pressure design:** Nothing should make a player feel obligated. If someone's having a bad day, they should be able to engage at whatever level feels comfortable
- **Voting/recognition:** Players can vote on things like best pose in a scene, flattering writing — creating positive reinforcement loops
- **New player onboarding:** Reducing the barrier for people unfamiliar with MUSH conventions. Modern web UX, helpful prompts, mentorship rewards

## What Exists
- **Models:** ConsentGroup, ConsentGroupMember, VisibilityMixin (abstract for content visibility) in consent app. Kudos models in progression app
- **APIs:** Kudos viewsets exist
- **Frontend:** Progression XP/Kudos page
- **Tests:** Kudos tests, visibility tests

## Built — Social Consent (#1141)
Per-category social consent settings UI and enforcement, merged [branch: feature-1141-social-consent-settings-ui-player-config].

- **Models (world/consent):** `SocialConsentCategory` (NaturalKey slug, staff-authored),
  `SocialConsentPreference` (OneToOne per tenure, master allow/deny switch),
  `SocialConsentCategoryRule` (per-category EVERYONE/ALLOWLIST mode),
  `SocialConsentWhitelist` (owner/allowed/category triples).
- **ActionTemplate.consent_category:** nullable FK tagging social templates with their category.
- **Enforcement:** `_tenure_blocks_actor` / `_social_consent_exclusions` in
  `src/actions/player_interface.py`; wired into social action target-spec building.
- **API:** `/api/consent/` — categories (read-only), preferences, category-rules, whitelist.
  `IsTenureOwner` permission scopes all writes to the requesting player's tenures.
- **Frontend:** `frontend/src/consent/` — Privacy tab at `/profile/privacy` with global toggle,
  per-category mode selectors, and per-category whitelist management.
- **Default categories + seed:** Romantic, Hostile, Manipulative, General seeded via
  `world/seeds/consent.py` (`arx seed dev` cluster `"consent"`). ActionTemplate tagging:
  Flirt→Romantic; Intimidate→Hostile; Deceive, Persuade→Manipulative;
  Perform, Entrance, Restore to Sense→General.
- **Admin:** `SocialConsentCategoryAdmin`, `SocialConsentPreferenceAdmin` (with category-rule
  inline), `SocialConsentWhitelistAdmin` (raw_id_fields for tenures + category).

## Built — Player Content Boundaries (#1771)
A private registry for hard content limits and treasured-subject flags, backing the
stakes-contract engine's `check_stake_boundaries` seam (#1770 PR4's allow-all stub).

- **Models (world/boundaries):** `ContentTheme` (NaturalKey slug, staff-authored —
  the small starter set: child endangerment, suicide/self-harm, sexual violence,
  torture), `PlayerBoundary` (owner `PlayerData`; `kind` HARD_LINE/ADVISORY; a hard
  line is structurally forced private and blocks any stakes contract whose
  `StakeTemplate.content_themes` intersects it), `TreasuredSubject` (owner
  `RosterTenure`; a specific entity — NPC, item, location, faction, custom — flagged
  as devastating-if-lost; matched by identity, not theme, and requires an explicit
  `TreasuredSignoff` rather than blocking outright).
- **Enforcement + resolution (world/stories):** `check_stake_boundaries` is now a
  real registry (was allow-all); `StakeTemplate.content_themes` M2M;
  `TreasuredSignoff` (soft-withdrawable pre-scene consent); a withdrawn sign-off
  routes only its stake to `WITHDRAWAL` at completion, siblings unaffected.
- **Sharing + scene aggregate:** both models reuse `world.consent.VisibilityMixin`
  (a hard line is always PRIVATE regardless); `scene_lines_and_veils` gives a scene
  an anonymized, owner-stripped union of shared advisories + treasured subjects
  (hard lines structurally excluded — the query never selects them).
- **GM availability:** `stake_availability` gives a GM counts-only tally
  (`available`/`blocked`/`needs_signoff`) — never a reason, player, or stake id.
- **API:** `/api/boundaries/` (content-themes, player-boundaries,
  treasured-subjects, scene lines-and-veils) + `/api/treasured-signoffs/` +
  `/api/beats/{id}/stake-availability/` (mounted on the stories router per
  ADR-0010's dependency direction).
- **Frontend:** `frontend/src/boundaries/` — a "Boundaries" tab on the Profile page
  (account-wide boundary authoring, per-tenure treasured-subject flagging, pre-scene
  sign-off), plus a `SceneLinesAndVeilsCard` on the scene detail page.
- **Privacy (ADR-0033/ADR-0086):** a hard line's reason is never surfaced to any GM
  or player, structurally (owner-scoped querysets with no staff carve-out,
  hard-line-excluded queries, counts-only GM reads) — not by convention.
- **Details:** `docs/systems/boundaries.md`, ADR-0086.

## Built — Telnet Onboarding Front Door (#2122)

Chargen/roster stay web-first by design, but the telnet front door itself was a dead end
with no signpost, and telnet-only accounts had no way to satisfy the web app's verified-email
gate. Three small, additive polish items (part of the #2112 launch-content-bootstrap slate):

- **Web pointers.** `settings.FRONTEND_URL` (promoted from five inline `env("FRONTEND_URL",
  ...)` calls in `settings.py`) now appears on the connection screen
  (`server/conf/connection_screens.py`) and the characterless post-login message
  (`typeclasses/accounts.py::at_post_login`), so a telnet-only player always has a path to the
  web roster/application/chargen flow.
- **`roster status`.** Own-pending-application status only (`CmdRoster`,
  `commands/account/account_info.py`) — roster browsing stays web-only, per the existing
  by-design boundary; this needed no listing/browsing UI, just a status line.
- **`account email <address>`.** A subverb on `CmdAccount` that sets/updates the account's
  primary allauth `EmailAddress` and sends the confirmation email — the telnet path to satisfy
  `can_apply_for_characters()`'s verified-email gate for `create <user> <pass>`-registered
  accounts (which collect no email otherwise). `can_apply_for_characters()` itself is
  unchanged.
- **XP balance.** `progression unlocks` now shows the caller's XP balance + last-5
  `XPTransaction` rows (previously it only leaked into failed-purchase error text).

Details: `docs/systems/roster.md`'s "Telnet Surface (#2122)" section, `docs/systems
/progression.md`'s Telnet Commands section, `commands/CLAUDE.md`.

## What's Needed for MVP
- ~~Friend list system~~ — SHIPPED (#1727): `FriendsTab`/`FriendButton` over
  `world/scenes/friend_views.py`
- Player finder — who's online, who's in scenes, who's looking for RP
- Visibility control UI — managing who can see you, your status, your activity
- Consent group management UI — creating, joining, managing content visibility groups
- Kudos expansion — more categories of positive behavior to reward
- Voting system — pose-of-the-scene, writing awards, community recognition. `WeeklyVote` +
  `VoteButton`/`VotesPanel` are built but unwired; reconciling the three applause axes
  (kudos/reactions/votes) is #2161
- New player onboarding flow — #1035 (spec-approved, mission-chain tutorial); web funnel
  polish is #2162
- Anti-harassment tools — blocking, muting, reporting
- Scene discovery — finding active public scenes to join; the discovery→presence bridge
  is #2163
- Social feed — what's happening in the game right now (new achievements, notable events, active scenes)

See `docs/audits/2026-07-10-webclient-rp-ux-audit.md` (epic #2155) for the full
webclient RP UX audit backing these issue references.

## Notes
