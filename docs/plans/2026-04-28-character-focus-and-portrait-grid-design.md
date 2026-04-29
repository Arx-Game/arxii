# Character Focus & Portrait Grid — Design Document

**Date:** 2026-04-28
**Status:** Design (brainstorm complete, plan to follow)
**Phase context:** Stories Phase 6 (renamed from "Group A — Frontend infrastructure cleanup" after design expanded scope)

---

## Problem

The web frontend has no first-class concept of "the character I am currently acting as." Today:

- The account payload (`/api/user/`) returns account-level fields only — no character/persona information.
- Search endpoints fall back to `account.get_puppeted_characters()[0]`, which only works when the user has a live Evennia session (telnet or in-game tab).
- `CreateBulletinPostDialog`, `BulletinPostCard`, `TableBulletin` all carry a `gmPersonaId={0}` stub because no persona id is exposed anywhere.
- GM-only routes (`/stories/gm-queue`, etc.) check role per-page; non-GMs get a 403 fallback because the nav can't tell who's a GM.
- The Evennia "play" CTA in the header is the legacy webclient affordance — wrong for a web-first game where the frontend *is* the game.

Underneath: the data model already supports the multi-character / multi-window model. Evennia accounts can puppet different characters per session, and `useGameSocket.ts` already keys websocket connections by character (`sockets[character]`). The infrastructure is there. The UI doesn't expose it.

## Goals

1. **Web parity with telnet's multi-session model.** A user can have multiple browser tabs open, each acting as a different character, all concurrently visible in-world to other players.
2. **Smooth character entry.** Click a portrait, you're focused on that character. Double-click, you enter the world. No `@ic` typing required.
3. **Strict role separation.** GMs cannot accidentally do GM-mode work while focused as their PC. Nav and tools follow the focused character's typeclass.
4. **Async management without "logging in."** Journal entries, relationship updates, story dashboards — all doable from a focused-but-not-puppeted state, no in-world presence created.
5. **Eliminate persona stubs and per-page 403 fallbacks.** Phase 5's `gmPersonaId={0}` and `NotGMPage` go away.

## Non-Goals

- **Inactive / deceased / WIP character interactions.** This pass only shows ACTIVE characters. Other statuses are filtered out entirely. Future phase can add async interaction with non-active characters if needed.
- **TEMPORARY persona handling in the lobby.** TEMPORARY personas are scene-bound, adopted in-game via spell/item after entering as a PRIMARY/ESTABLISHED persona. Expire on logout. Not relevant to portrait grid.
- **Web-side character creation flow.** WIP characters (in chargen / pending application) surface as a `RosterApplication` "Continue creation: Bob" item in the ProfileDropdown, not the portrait grid. The chargen flow itself is unchanged.
- **Channel/covenant chat.** Deferred to a later phase.

## Architecture

### Two distinct "active" levels per browser tab

| Level | Trigger | Tab state | Server state | Telnet visibility |
|---|---|---|---|---|
| **Focused** | Single-click portrait | `focusedCharacterId`, `selectedPersonaId` | None | None — character is "logged out" in-world |
| **Puppeted** | Double-click portrait | Above + `isPuppeted: true` | Evennia session puppet | Character appears in last-logged-off room (or starting room) |

Focus is sufficient for asynchronous IC actions: writing journal entries, posting bulletins, authoring narrative messages, updating relationships, viewing story dashboards. These do not create in-world presence.

Puppeting is required for synchronous in-world IC: speaking in rooms, posing, entering scenes, traversing exits. This is the existing Evennia puppet model, unchanged.

A tab can be:
- **OOC** (no focus) — only OOC nav (account settings, character apps, browse).
- **Focused, not puppeted** — character is selected for async work; nav reflects character type; in-world presence absent.
- **Focused and puppeted** — full in-world play; identical to today's `@ic` behavior, just with a portrait click instead of typing.

### Per-tab independence

Each browser tab has its own `{ focusedCharacterId, selectedPersonaId, isPuppeted }` state. Tab A focused on PC has PC-only nav; tab B focused on GMCharacter has GM nav. Multiple tabs concurrently puppeting different characters all show up in-world independently — same as opening multiple telnet clients today.

State storage: tab-scoped Redux slice (or React context), persisted to `sessionStorage` (which is per-tab, unlike `localStorage`). On tab open, frontend hydrates from `sessionStorage` and validates against the account's `available_characters` list.

### Strict role separation

Nav visibility is driven by **the focused character's typeclass**, not by account-level capability flags:

- Focused on `Character` (PC) → PC nav (game, journals, relationships, story participation, mail)
- Focused on `GMCharacter` → GM nav (story author editor, GM queue, table management, offer inbox, AGM claim review)
- Focused on `StaffCharacter` → staff admin nav (era admin, staff workload, full GM nav as superset)
- Focused on NPC → restricted IC nav (typically just basic in-world commands when puppeted, but visible in grid for management)
- No focus → OOC nav only (account settings, character apps, browse public stories)

This eliminates the failure mode "GM accidentally posts a bulletin from their PC's persona thinking they're acting as GM." If you're focused on the PC, you literally cannot see the GM bulletin authoring UI.

The existing `is_staff` account flag is kept for legacy reasons (some non-character-scoped admin pages still reference it), but new work derives role from focused character. `is_staff` will be retired in a follow-up when those legacy admin surfaces migrate.

### Account payload shape

```ts
interface AccountData {
  // Existing
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  email: string;
  email_verified: boolean;
  can_create_characters: boolean;
  is_staff: boolean;  // legacy — phase out later
  avatar_url?: string;

  // New in Phase 6a
  available_characters: AvailableCharacter[];
  pending_applications: PendingApplication[];  // surfaces in ProfileDropdown
}

interface AvailableCharacter {
  id: number;
  name: string;
  portrait_url: string | null;
  character_type: "PC" | "GM" | "STAFF" | "NPC";  // from typeclass
  roster_status: "Active";  // only ACTIVE in this pass
  personas: Persona[];
  last_location: { id: number; name: string } | null;
  currently_puppeted_in_session: boolean;
}

interface Persona {
  id: number;
  name: string;
  persona_type: "primary" | "established";  // TEMPORARY excluded
  display_name: string;
}

interface PendingApplication {
  id: number;
  character_name: string;
  status: "pending" | "in_progress";
  resume_url: string;
}
```

`character_type` derivation in the backend:

```python
# src/web/api/serializers.py
TYPECLASS_TO_CHARACTER_TYPE = {
    "typeclasses.gm_characters.GMCharacter": "GM",
    "typeclasses.gm_characters.StaffCharacter": "STAFF",
    # NPC detection: TBD — see "Open implementation question" below
}

def derive_character_type(character_obj) -> str:
    return TYPECLASS_TO_CHARACTER_TYPE.get(
        character_obj.db_typeclass_path, "PC"
    )
```

`available_characters` queryset filters to ACTIVE roster only:

```python
# src/world/roster/managers.py — already exists as `available_characters()`
# in this pass: further filter to roster name == ACTIVE
```

### Portrait grid component

Replaces the Evennia "play" CTA. Lives in the header (or a sidebar panel — exact placement decided in 6b).

**Type tabs** (only shown if user has ≥1 character of that type):
- Regular player: no tabs (single grid of PCs)
- GM account: "GM | PCs" or "GM | PCs | NPCs"
- Staff account: "Staff | PCs" or "Staff | PCs | NPCs"

Default tab: GMCharacter for GMs, StaffCharacter for staff, otherwise PCs. Possibly overridden by "tab with most pending notifications," but that's a 6b polish question.

**Per-portrait interactions:**
- **Single-click**: Focus this tab on that character. Update tab state. Nav re-renders for the character's type. No server call beyond persisting the focus choice (or it stays purely client-side via sessionStorage — TBD in 6b plan).
- **Double-click**: Puppet. Open websocket if not already open, send `@ic <name>`, character enters world. Existing `useGameSocket` flow.
- **Right-click** (only if `personas.length > 1`): Persona selector menu — PRIMARY + ESTABLISHED. Updates `selectedPersonaId` in tab state.

**Indicators:**
- "Currently puppeted in another session" badge on portraits puppeted elsewhere (still selectable — user can take over).
- "Focused here" highlight on the portrait this tab is focused on.

### `puppet.changed` websocket event

When `@ic <name>` runs (from telnet, web command box, or double-click), the server broadcasts a `puppet.changed` event over the affected account's websocket connections so other tabs can update their "currently puppeted in another session" indicators in real-time.

```python
# Pseudocode in puppet_character_in_session
def puppet_character_in_session(self, character, session):
    success, msg = ...
    if success:
        for sess in self.sessions.all():
            sess.msg(meta={
                "type": "puppet.changed",
                "session_id": session.sessid,
                "character_id": character.id,
                "character_name": character.name,
            })
    return success, msg
```

## Sub-phase split

This is genuinely larger than Phase 5. Three sub-phases, each its own PR.

### 6a — Backend account payload + character classification

- Extend `AccountPlayerSerializer` with `available_characters` (portrait, type, status, personas, last_location, in-use flag) and `pending_applications`.
- Detect `character_type` from typeclass (`GMCharacter`, `StaffCharacter`, NPC TBD, default PC).
- Expose `personas` per character (PRIMARY + ESTABLISHED).
- Add `puppet.changed` event broadcast on `puppet_character_in_session` and `unpuppet_object`.
- Update `frontend/src/evennia_replacements/types.ts` with new fields.
- Tests: serializer tests for each character_type, persona list, status filter, in-use flag accuracy.

**Definition of done:** `/api/user/` returns the full new payload; existing pages still render unchanged because they don't yet read the new fields.

### 6b — Portrait grid + tab-scoped focus/puppet

- `CharacterPortraitGrid` component with type tabs.
- Tab-scoped Redux slice for `{ focusedCharacterId, selectedPersonaId, isPuppeted }`, persisted to `sessionStorage`.
- Header `CharacterChip` showing current focus + persona, with a "switch" affordance.
- Right-click persona menu (only when >1 persona).
- Replace Evennia "play" CTA path with portrait grid surface.
- Pending applications surface in ProfileDropdown.
- WS handler for `puppet.changed` updates "in use elsewhere" indicators.

**Definition of done:** A user can log in, see their portraits, single-click to focus, double-click to puppet, right-click to switch persona. Multiple tabs work independently.

### 6c — Wire it everywhere

- Bulletin / narrative / offer dialogs read `selectedPersonaId` from tab state; remove `gmPersonaId={0}` stubs.
- `<RoleRoute characterTypes={["GM","STAFF"]}>` route guard derived from focused character.
- Nav menu filters by focused character type (PC, GM, Staff).
- Remove per-page 403 fallback pages (`NotGMPage` etc.) where the route guard now handles it.
- Update tests + CLAUDE.md docs.

**Definition of done:** No `gmPersonaId={0}` stubs anywhere; non-GMs don't see GM nav links; per-page 403 fallbacks removed.

## Open implementation questions

These should be answered during 6a planning, not now:

1. **NPC typeclass detection.** Is there a dedicated `NPC` typeclass, or are NPCs distinguished by some other field (roster type, flag on RosterEntry)? The 6a plan needs a concrete check.
2. **Portrait URL source.** Where do character portraits come from today? `Persona.portrait_url`? `CharacterSheet.avatar_url`? `TenureMedia`? The 6a serializer needs a single canonical source.
3. **Last-location source.** `RosterEntry.last_puppeted` exists per `general_views.py:94` — does it record the room, or just timestamps? If just timestamps, where does the actual room come from on logoff?
4. **Pending applications shape.** What does `RosterApplication` expose for "resume URL"? May need a new endpoint or just a frontend route convention (`/character-creation/:applicationId/continue`).

## Risks

- **Tab-scoped state correctness.** Redux + sessionStorage is the standard pattern but easy to get wrong (state leaking between tabs via localStorage by accident, hydration races on tab open). 6b plan must include explicit sessionStorage tests.
- **`puppet.changed` event delivery.** If the broadcast misses tabs, "in use elsewhere" indicators go stale. Acceptable — user can refresh; not a correctness issue, just a polish one. But worth a manual test pass.
- **Performance of `available_characters`.** Could fan out to many queries if not prefetched (each character → roster_entry → roster, persona list, last_puppeted, portrait). Use `Prefetch(to_attr=...)` aggressively per project conventions.
- **Strict role separation breaking existing flows.** If a GM has a half-finished bulletin draft as PC and then clicks the GM portrait, the draft is gone (different tab state). Acceptable per the design — strictness is the feature, not the bug.

## Future work (not Phase 6)

- Inactive / Frozen / Deceased character async interactions (read-only journal access, etc.)
- Cross-tab presence indicators ("your other tab just entered the throne room")
- Web-only persona creation (TEMPORARY personas via web spell/item UI)
- Multi-window scene awareness (notifications when one of your other characters is mentioned)
- Drag-to-rearrange portrait order
