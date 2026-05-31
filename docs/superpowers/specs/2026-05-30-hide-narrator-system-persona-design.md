# Hide the combat Narrator system persona from persona pickers (#643)

**Status:** design — decisions locked, ready for plan
**Branch:** `worktree-feature-643-hide-the-combat-narrator-system-persona` (git worktree)
**Date:** 2026-05-30

## Goal

The #557 PR created a singleton "Narrator" persona (`world.combat.narrator.get_or_create_narrator_persona`) to author combat OUTCOME interactions. It is a real `Character` + `CharacterSheet` + PRIMARY `Persona`, so it can appear in the persona-picker list (`PersonaViewSet`). It should be hidden from persona pickers/lists — while its authored interactions keep displaying in the scene log (that is #557's whole point).

## Decisions (user-ratified)

1. **General `is_system` boolean on `Persona`**, not a Narrator-specific hack. Semantics: "an OOC system/narrator/GM identity." The Narrator sets it now; GM/staff narrator-personas can set it later (field is general). Orthogonal to the IC `properties` M2M (those describe what a character *is* in-world; this is an OOC structural flag) — so not reinventing `Property`.
2. **Hide identity from pickers, NOT content from the log.** `is_system` excludes the persona from persona-list/picker surfaces. It must NOT touch interaction-display prefetches — system/Narrator-authored content renders normally in the scene feed.
3. **Scope = `PersonaViewSet` only** (corrected after code verification — see below). GM-persona flagging deferred (no GM-emit surface exists yet to wire).

## Verified leak analysis (code, not assumption)

A recon pass initially flagged three surfaces; reading the actual code narrowed it to one:

| Surface | File | Leaks Narrator? | Why |
|---|---|---|---|
| `PersonaViewSet.get_queryset` | `scenes/views.py:264-269` | **YES** | Plain `Persona.objects.select_related(...)`, no system filter → Narrator appears in the picker list. **Fix here.** |
| `character_data._get_personas` | `evennia_extensions/data_handlers/character_data.py:88` | No | Filters `character_sheet__character=self.obj` — per-character; only returns the Narrator when inspecting the Narrator itself. |
| `random_scene` persona pools | `world/progression/services/random_scene.py:44-113` | No | Every pool is gated through `RosterEntry` (active tenure / account ownership / relationships). The Narrator has no `RosterEntry`, so it can never be picked. |

Filtering the latter two would be dead defensive code on paths that cannot surface the Narrator (YAGNI). Roster-gating already protects them.

`is_system` is genuinely ABSENT today (grep: no `is_system`/`system_entity`/`is_npc` on `Persona`).

## Anti-reinvention ledger

| Surface | Verdict | Evidence |
|---|---|---|
| existing system/hidden-entity mechanism on Persona | ABSENT → add | grep: none on `Persona` (`classes.CharacterClass.is_hidden` is unrelated) |
| `Persona.properties` M2M (IC tags) | BUILT & WIRED — intentionally NOT reused | `scenes/models.py:213`; IC-descriptive, wrong axis for an OOC structural flag |
| `PersonaViewSet` / `PersonaFilter` | BUILT & WIRED | `scenes/views.py:252`, `scenes/filters.py:57` |
| `get_or_create_narrator_persona` | BUILT & WIRED | `combat/narrator.py:16-36` (#557) |
| `Persona.is_system` field + `PersonaQuerySet.exclude_system()` | ABSENT → add | — |

## Design

**Model** (`world/scenes/models.py`):
- Add `is_system = BooleanField(default=False, db_index=True, help_text=...)` to `Persona`.
- Add a `PersonaQuerySet(models.QuerySet)` with `exclude_system()` → `self.filter(is_system=False)`, and set `objects = PersonaQuerySet.as_manager()`. (Confirm `Persona` doesn't already declare a custom manager — it currently does not; uses the default. SharedMemoryModel-compatible: use `PersonaQuerySet.as_manager()`.)
- Schema migration only — no data migration (per the skip-data-migrations rule; the Narrator row gets the flag at creation / self-heals on lookup).

**Narrator** (`world/combat/narrator.py`):
- New Narrator: after `create_character_with_sheet(...)`, set `persona.is_system = True; persona.save(update_fields=["is_system"])`.
- Existing Narrator (early-return path): self-heal — if found and not `is_system`, set it and save. Keeps correctness whether or not a Narrator predates this change.

**Picker exclusion** (`world/scenes/views.py`):
- `PersonaViewSet.get_queryset()` → append `.exclude_system()` to the existing chain.

**Not touched:** `SceneViewSet` interaction prefetches, `InteractionViewSet`, `character_data`, `random_scene` — all either display content (must keep showing) or are roster-gated (cannot leak).

## Testing

- **Model** (`scenes/tests`): `PersonaQuerySet.exclude_system()` filters out an `is_system=True` persona, keeps normal ones.
- **Narrator** (`combat/tests/test_narrator_persona.py`, extend): `get_or_create_narrator_persona()` returns a persona with `is_system=True`; a pre-existing non-system Narrator row is healed to `is_system=True` on next call.
- **ViewSet** (`scenes/tests/test_views.py`, mirror `_create_owned_persona` pattern): the Narrator does NOT appear in `PersonaViewSet` list; a normal owned persona does.
- SQLite tier locally (`just test-fast scenes combat`); CI for PG parity.

## Scope / follow-ups

**In:** `Persona.is_system` field + migration; `PersonaQuerySet.exclude_system()`; Narrator sets/heals the flag; `PersonaViewSet` excludes; tests.

**Deferred (file as issue):** flag GM/staff-authored personas as `is_system` once a GM-emit-persona surface exists. Field is ready; no consumer to wire today.
