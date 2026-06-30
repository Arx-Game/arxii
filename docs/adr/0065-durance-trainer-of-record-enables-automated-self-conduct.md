# A trainer-of-record bound to a room (DuranceTrainingSite) enables automated self-conduct
# of the Ritual of the Durance from telnet

A character advancing through the Ritual of the Durance needs a qualified officiant (same
Path lineage, higher level — enforced by the unchanged `assert_can_officiate` gate).
Requiring a live higher-level PC to be online and present was the only path before #1700,
which excluded solo or asynchronous play entirely. We decided to bind a trainer-of-record
(`CharacterSheet`) to a room via `DuranceTrainingSite`; `convene_durance_at_site` drafts
the Durance `RitualSession` with that trainer as initiator (officiant), and the inductee's
`ritual join` auto-fires via `DuranceAdapter.should_auto_fire` — so the rite still runs
through the full ritual session lifecycle (draft → join → fire → `advance_class_level_via_session`)
and the `assert_can_officiate` integrity gate is never bypassed. We rejected (a) requiring a
live officiant only — excludes solo/async play; and (b) self-serve with no officiant of
record — bypasses `assert_can_officiate`, allowing inductees to advance without any Path-lineage
and level gate. Both rejected alternatives were untenable: (a) is a UX cliff that blocks
telnet-parity, (b) breaks the game's advancement integrity. The live-officiant ceremony
(`ritual draft` → `ritual join` → `ritual fire`) remains fully supported alongside
site-convened sessions. See also ADR-0001 (both surfaces converge on `advance_class_level_via_session`)
and ADR-0063 (the level-3 semi-crossing that site-convened sessions may trigger via `path=<name>`).

> Status: accepted · Source: #1700 design 2026-06-30 · Confidence: built and wired —
> `DuranceTrainingSite` in `world/progression/models/advancement.py`,
> `convene_durance_at_site` + `NoDuranceSiteError` in `world/progression/services/advancement.py`,
> `DuranceAdapter` in `commands/ritual_adapters.py`, `CmdDurance` in `commands/durance.py`;
> proven by `integration_tests/pipeline/test_durance_telnet_e2e.py`.
