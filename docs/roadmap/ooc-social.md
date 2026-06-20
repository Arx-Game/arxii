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

## What's Needed for MVP
- Friend list system — explicit friend tracking with online status
- Player finder — who's online, who's in scenes, who's looking for RP
- Visibility control UI — managing who can see you, your status, your activity
- Consent group management UI — creating, joining, managing content visibility groups
- Kudos expansion — more categories of positive behavior to reward
- Voting system — pose-of-the-scene, writing awards, community recognition
- New player onboarding flow — guided introduction to the game and its systems
- Anti-harassment tools — blocking, muting, reporting
- Scene discovery — finding active public scenes to join
- Social feed — what's happening in the game right now (new achievements, notable events, active scenes)

## Notes
