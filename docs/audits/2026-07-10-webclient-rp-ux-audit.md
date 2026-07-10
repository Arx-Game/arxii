# Webclient RP UX & Playability Audit

**Date:** 2026-07-10 — **Tracking epic:** [#2155](https://github.com/Arx-Game/arxii/issues/2155)
**Scope:** the web client's UX for the roleplay loop — joining and participating in scenes,
following multiple conversations, scene→combat transitions, browsing while in a scene, pose
feedback/journals/messengers, rituals/relationships/threads, magic status, social actions,
registration/character application, and tutorial/onboarding substrate. Built from a
nine-dimension code sweep (each dimension walked as a player journey with
`[BUILT & WIRED]` / `[BUILT, NOT WIRED]` / `[ABSENT]` labeling per the
`verify-against-code` convention).
**Complements:** `2026-06-25-player-reachability-coverage.md` (capability reachability —
"can a player do X at all"). This audit measures the next axis: **for capabilities that are
reachable, is the experience any good while actually roleplaying?**

---

## Headline finding

Most of the machinery for great RP UX is **already built** — conversation threading, consent
cards, reactions/endorsements, the combat rail, ritual sessions, the relationship action
layer. The dominant failure modes are:

1. **Placement** — features live on routes players aren't on. The live `/game` view and the
   `/scenes/:id` page each hold half the game, and the half a player needs is always on the
   other one.
2. **Silence** — mutating actions succeed with no visible acknowledgment: combat starts,
   resources drain, regard shifts, applications submit, and the UI shows nothing.
3. **The front door** — the registration→application→first-login funnel is the least
   polished surface in the product, and the onboarding/tutorial layer is placeholder copy
   with dead links (the real tutorial is #1035, spec-approved, missions-based).

## The two-surface split (structural root cause)

| Capability | `/game` (live view: room, exits, presence, puppet tabs) | `/scenes/:id` (pose feed page) |
|---|---|---|
| Conversation threading (`useThreading`/`ThreadSidebar`/`ThreadFilterModal`) | ABSENT — flat monospace log; `ConversationSidebar.tsx` is a static placeholder | BUILT & WIRED |
| Markdown rendering of composed poses | ABSENT (`EvenniaMessage.tsx` — literal `**` renders) | BUILT & WIRED (`FormattedContent`) |
| Action panel / cast flow / target picker | ABSENT | BUILT & WIRED (`ActionPanel.tsx`) |
| Places (sub-location) bar, join/leave | ABSENT | BUILT & WIRED (`PlaceBar.tsx`) |
| Tabletalk composer mode | hardcoded off (`isAtPlace={false}` TODO, `CommandInput.tsx`) | gated the same way |
| Reactions / kudos chip / endorsements per pose | ABSENT | BUILT & WIRED (`PoseUnit.tsx`) |
| Room context, exits, movement | BUILT & WIRED | ABSENT |
| Presence ("Who"), events, codex, status side tabs | BUILT & WIRED (`SidebarTabPanel`) | ABSENT |
| Multi-puppet session tabs w/ unread dots | BUILT & WIRED (`GameWindow.tsx`) | n/a |

The roadmap's threading design (`rp-scenes.md`: "in a room with 30 people, follow just the
threads you care about") targeted the live view; the implementation landed on the side page.
Resolving this split is **#2156**, the structural core of the slate.

## Per-dimension summaries

### 1. Joining and participating in scenes (#2156, #2163)

- Discovery is wired (homepage `ScenesSpotlight`, `/scenes` list) but **there is no bridge to
  presence**: no join/travel affordance anywhere; location renders as plain text in the scene
  list and presence panel; reaching a scene = manual exit-by-exit navigation on `/game`.
  Participation is implicit (`ensure_scene_participation()` on first pose while co-located).
- Composer is genuinely good: rich-text toolbar + shortcuts, xterm color picker, `@name`
  autocomplete with avatars, mode selector (pose/say/emit/whisper/tabletalk) — but the mode
  selector and action-attachment only mount on `/scenes/:id`.
- Per-thread unread is stubbed (`useThreading.ts` `unreadCount: 0 // TODO`).

### 2. Scene→combat transition (#2157)

- **Combat starts silently.** The hostile-cast response carries `{encounter: {id, status}}`
  (`world/scenes/action_views.py:601-605`); the frontend's `CastResponse` type omits the
  field and `performCast.onSuccess` never reads it. No toast/banner/redirect; only italic
  OUTCOME lines in the feed.
- `/scenes/:id/combat` itself is strong (pose feed + combat rail side by side, live
  initiative, declarations, outcome banner) but nothing links to it; no return-to-scene link
  when combat ends; the battle map `/scenes/:id/battle` (#2009) is linked from nowhere;
  duel challenges (`useDuelChallengeInbox`) poll only inside `CombatScenePage`, so
  challenges are invisible unless you're already there.
- Posing during combat works (same composer/feed components) — the simultaneity goal is met
  *once the player finds the route*.

### 3. Browsing while in a scene (#2156 + profile-link fold-ins)

- WebSocket + Redux message buffers survive route navigation (module-scoped sockets), but
  `/scenes/:id` loses thread-filter state and scroll position on any navigate-away
  (local `useState`, no `ScrollRestoration` anywhere).
- `/game`'s drill-in `CharacterFocusView` shows only name + worn items (fuller profile
  flagged as follow-up in-file) and has no link to `/characters/:id`; `PersonaContextMenu`
  on pose names has RP actions but **no "View profile" item** — the cheapest high-leverage
  fix in this audit.
- No unread/new-activity signals for events/tidings/scenes outside the global header badges;
  no pop-out/split-view support (`window.open` count in app code: 0).

### 4. Pose feedback, journals, messengers (#2160, #2161)

- **Giving kudos is exemplary** — one-tap `ReactionStrip` on every pose, ADR-0033-respecting
  anonymized attribution. But *seeing why you got kudos* requires navigating to `/xp-kudos`.
- **Three parallel applause systems disagree**: kudos chip, emoji reactions (what
  `HighlightReel` "top poses" actually ranks by), and the fully-built-server-side
  `WeeklyVote` heart economy whose `VoteButton`/`VotesPanel` components are **imported
  nowhere**; no top-voted endpoint exists.
- **`world.journals` (diary/praise-retort, weekly XP) has zero web frontend**; telnet
  (`journal write`) is complete. The `/journal` route is a decoy — it's the *missions*
  ledger, an unrelated system sharing the name.
- **No messenger concept exists**; `PlayerMail` compose/inbox is at `/profile/mail` with no
  in-scene compose, no unread badge, no arrival push.
- Latent gotcha: `KudosTransaction.awarded_by` serializes raw `username`; all callers pass
  `None` by convention only — no structural guard (ADR-0033 risk if a future caller passes
  an account).

### 5. Rituals, threads, relationships (#2159)

- SCENE_ACTION rituals (e.g. anima recovery) cast inline — good. Multi-participant ritual
  sessions (draft→invite→accept/decline→fire) are well-built dialogs but **exiled from the
  scene**: reachable only via header inbox; no marker in the scene where the ritual was
  proposed; `/rituals` absent from top nav (only entry: own sheet → Magic tab footer).
- **Bug:** `WeaveThreadWizard`'s RELATIONSHIP_TRACK anchor posts a generic
  `RelationshipTrack` catalog id where the backend resolves
  `RelationshipTrackProgress.objects.get(pk=…)` (`magic/serializers.py:885-901`) — disjoint
  pk spaces, and the wizard never asks *with whom*. Presents as fully built; fails on
  submit. Telnet's `track=<partner>/<track>` grammar is correct. RELATIONSHIP_CAPSTONE
  weaving is honestly labeled deferred, but capstone *creation* has no web path either.
- **Relationship state is invisible on the web**: `RelationshipsSection.tsx` renders a
  legacy `string[]` with "TBD"; the full REST family (`CharacterRelationshipViewSet`,
  `RelationshipUpdateViewSet`, capstones, tracks) has zero frontend consumers. The
  relationship-authoring loop (impression/development/capstone/redistribute) shipped
  web+telnet at the action layer (PR #1536 — this **corrects the 2026-06-25 audit's
  NO-SURFACE row**), but the web side is viewset-only with no UI; writeup kudos/complain
  endpoints are uncalled.
- **The bright spot:** rel/plus / rel/neg as one-click valenced emoji on poses
  (`ReactionsFooter` → `RelationshipBumpAction`, #2132) is the model in-scene affordance —
  though its success is silent (response discarded; see #2158).

### 6. Magic status and technique use (#2156, #2158)

- No cast affordance on `/game` at all; casting = navigate to `/scenes/:id`, then 6–8
  interactions through nested popovers.
- **Anima/resonance never live-update on spend**: `useCharacterAnima` /
  `useCharacterResonances` have no invalidation wired to cast/pull mutations or
  `ACTION_RESULT` WS frames (combat mutations invalidate only `combatKeys`; the imbue path
  invalidates correctly — the cast/pull path is the gap).
- Design ruling respected and preserved: anima is a qualitative band outside the sheet
  ("the sheet describes; the scene does") — the fix is freshness, not numerals.
- Aura perception is a static sheet privacy flag; no in-fiction "read aura" action —
  low-urgency, partly by design.

### 7. Social actions in RP (#2158)

- Dispatch is well-converged (persona context menu + action panel + attach-to-pose, all via
  the consent flow / `action.run()`); the consent card (plausibility bands + resist effort)
  is good fidelity.
- **Outcomes are invisible**: NPC disposition (`social_disposition.py`) and player regard
  bumps mutate with zero UI feedback — no toast, no effect row kind, nothing in the outcome
  detail panel. The whole point of a social action has no confirmation.
- Typed verbs silently become prose: the composer's `KNOWN_COMMANDS` whitelist
  (pose/say/emit/whisper/tt) absorbs `intimidate Bob` into pose text with no signal.
- `PersonaContextMenu` silently omits prerequisite-unmet actions (panel shows reason
  tooltips) and reads available-actions from cache only — empty menu until the action panel
  has been opened once.
- Non-GM participants have no round-state visibility in structured scenes (`active_round`
  consumed only by the GM-gated `RoundSettingsDialog`).
- Parity: Seduce is web-only (no telnet command; #1697 asymmetry).

### 8. Registration and character application (#2162)

- Homepage hero is Evennia boilerplate; `NewPlayerSection` is placeholder copy with two dead
  links to a nonexistent `/how-to-start` route (404).
- Registration: server-side password rules surface only as generic post-submit errors.
- Two unreconciled character paths: roster apply (silent success — form just clears; allows
  duplicate submissions; staff review in raw Django admin; emails every state change) vs
  11-stage CG (polished staff review app; **no notification on approval**). No "My
  Applications" view despite `pending_applications` shipping unread on `/api/user/`.
- CG stages ship blank on fresh deploys (`CGExplanation` unseeded; all copy falls back to
  `''`). Seed content must ride the standard cluster-seeder path.
- No first-login moment; zero-character accounts get full game chrome with an empty
  switcher. Orphaned all-TODO `roster/pages/CharacterCreatePage.tsx` is unrouted dead code.
- The 2026-06-25 audit's "roster `apply` returns 204 without saving" bug is **fixed** — the
  endpoint now creates the application and triggers emails.

### 9. Tutorial and onboarding substrate (#1035)

- No tutorial exists on either surface; telnet `help` carries two generic Evennia entries;
  Evennia's `tutorial_world` contrib is unused; MSSP still advertises "NEWBIE FRIENDLY: 0".
- **#1035 (spec-approved) is the right answer and the substrate verdict holds**: the mission
  system (dual-surface parity, chain prerequisites, world-anchored givers, boards, directed
  summonses, legend-risk floor) is the tutorial engine; external-act beats are the one new
  surface. Achievements complement it for milestone celebration once their notification UI
  exists; Codex is IC lore, not a mechanics-help system.
- This slate is sequenced to clear the ground the tutorial walks across: #2156 (the scene
  surface the tutorial teaches), #2157 (combat wayfinding), #2162 (the funnel before the
  tutorial's first step).

## Concrete bugs (fix-now, distinct from journeys)

1. Weave-into-relationship pk-space mismatch (`WeaveThreadWizard.tsx` vs
   `magic/serializers.py:885-901`) — folded into #2159.
2. WS pose path resolves scene by the character's room, not the viewed page's `sceneId`
   (`CommandInput.tsx:149-153`) — folded into #2156.
3. Markdown unrendered in `/game` feed (`EvenniaMessage.tsx`) — folded into #2156.
4. Dead `/how-to-start` links (`NewPlayerSection.tsx:30,49`) — folded into #2162.
5. `PersonaContextMenu` empty-until-cache-populated — folded into #2158.
6. Discarded `CastResponse.encounter` — folded into #2157.

## Issue slate

| Issue | Theme |
|---|---|
| #2156 | One play surface: threading/actions/casting where players play (structural core) |
| #2157 | Combat announces itself: scene→combat→scene transitions |
| #2158 | The game answers back: live feedback for social/magical outcomes |
| #2159 | Relationships visible and writable from the scene |
| #2160 | Journals and letters without leaving the scene |
| #2161 | One applause economy: kudos/votes/reactions + top poses |
| #2162 | The front door: homepage, registration, application status |
| #2163 | Discovery→presence bridge |
| #1035 | (pre-existing, spec-approved) dual-surface tutorial capstone |

## Stale-doc flags (fix-on-sight)

- `docs/roadmap/ooc-social.md` "What's Needed for MVP" lists the friend list as unbuilt —
  friends shipped (#1727, `friend_views.py`); corrected in this PR.
- `docs/audits/2026-06-25-player-reachability-coverage.md` lists the relationship-building
  loop as NO-SURFACE — superseded by PR #1536 (web+telnet at the action layer; web *UI*
  remains absent, which is #2159's scope, a different claim); annotated in this PR.
