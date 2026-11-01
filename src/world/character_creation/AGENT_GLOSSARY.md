# Character creation: glossary

Canonical terms for `world.character_creation`. The map is `AGENT_GLOSSARY_MAP.md` at the
repo root.

**Beat** (`LifeBeat`, #4124):
One beat of a life: a prompt over priced distinction offers, pooled under a life stage,
authored once in the shared library and offered to every Beginning that does not
exclude it. Its answers are the Backgrounds chapter's offers opened by the beat.
_Avoid_: question, prompt (that is the Upbringing's bespoke `OriginTemplateSlot`),
milestone.

**Life stage** (`LifeStage`, #3660, #4124):
Childhood, youth, before the Glimpse, at the Glimpse, since the Glimpse: the stage a beat
is pooled under and a tie's tag. _Avoid_: phase, era, chapter (a chapter is a CG offers
chapter).

**Unknown beat** (`CharacterOriginSlot.unknown`, #4124):
A beat the character took but does not remember; the sheet shows it blank and a `Secret`
naming it (`resolves_beat`) fills it in when the subject learns it. _Avoid_: skipped,
blank, amnesia flag.

**Frame** (`Beginnings.frame`, #4395):
The prose every character who starts from a beginning shares, read at the pick beside
the beginning's **station** (`Beginnings.station`, one line of standing). It moved here
from the route's `frame_narrative`. _Avoid_: upbringing frame, intro.

**Strike** (`Beginnings.strikes_childhood` / `strikes_youth` / `strikes_adulthood`, #4395):
A whole stage a beginning leaves out of the life grids; its beats are absent, not greyed
(`struck_stages()`). A single beat is left out with a `LifeBeatExclusion` instead.
_Avoid_: locked stage, hidden stage.

**Route** (`OriginTemplate`, #3617, #4395):
The beginning's family-path record (which paths, the parentage, the path-scoped prompts
and priced answers), assigned with the beginning (`route_for_beginning`/`assign_route`).
Staff still call it an Upbringing in the builder; a player never picks one. _Avoid_:
Upbringing (as a player term), template (in player copy).

**General write-in** (`questionnaire.is_general_write_in`, #4395):
A free-text question asked on every family path with nothing to pick: retired from
creation, never shown, left out of the route payload. _Avoid_: lore question, prompt
(the kept kind).

**Career points** (`LifeBeat.picks_scale_with_age`, `offers.age_pick_allowance`, #4395, #4829):
What an age-scaled beat allows: one point at or under nineteen, one more for every five
full years lived past it, none past fifty-nine (`AGE_PICKS_FROM_AGE`,
`AGE_PICKS_YEARS_PER_PICK`, `AGE_PICKS_CAP_AGE`). A point buys a card on the beat or a rank
on one, so the beat counts ranks (`beat_pick_conflicts`, `BeatPoolEntry.allowance_is_points`);
the age floor (`youngest_age_for_points`) keeps the age at or above the points held.
`beat_allowance` reads it, one-of or any otherwise. _Avoid_: age allowance (the old name),
age slots, experience picks, career slots.

**Kin row** (`draft_data["kin_rows"]`, `KinRowKind`, #4395, #4870):
A person seated beside the parents in the Lineage step: a twin (`TwinFate`, alive or dead),
a spouse (`SpouseFate`; separated stands in law apart, fled reads missing), a betrothed
(`BetrothedFate`: promised, dead, missing, broken off; a union of the **betrothal kind**), a
child (`ChildFate`); finalize's `_bind_kin_rows` writes them into the kinship graph. The
named parents carry a **parent fate** of their own (`ParentFate`, `line_parent_fate` /
`other_parent_fate`), where every "a parent died or vanished" story lives instead of a
card. _Avoid_: kin beat, family slot (that is a staff Vacancy), parent card.

**Struck-stages text** (`Beginnings.struck_stages_text`, #4830):
What the life page shows in place of the stage rows when a beginning strikes every stage (the Sleeper's). _Avoid_: frame (that is the prose at the pick), absent-life text.

**Recent History** (`draft_data["recent_history"]`, `RECENT_HISTORY_MAX_LENGTH`, #4830):
The optional free text a life ends on, the hooks a player wants picked up; written at finalize as the lead-in paragraph of `Profile.background`, public. _Avoid_: since the Glimpse (the cut stage), hooks (those are GM-seeded, #4397).

**Stage description** (`draft_data["stage_descriptions"]`, `CharacterOriginSlot.life_stage`, #4872):
The one paragraph a player writes for a whole stage of the life, printed under the stage's
name in the told background before its beats. A row with a stage and no slot or beat.
_Avoid_: beat line (the per-beat sentence), stage note.

**Cover story** (`draft_data.beats[<id>].cover_offer_id`, `CharacterDistinction.is_cover`, #4872):
The answer on the same row a secret pick hides behind; held at finalize as a card that grants
nothing, listed on a stranger's sheet where the secret is absent. Null means Unremarkable,
the row's no-cost card. _Avoid_: fake answer, alias (a second face is a persona).

**Secret mark** (`draft_data.beats[<id>].secret_offer_ids`, #4872):
A pick on a beat the player marks secret at creation; minted a Secret at finalize the way a
`secret_by_default` card is. _Avoid_: hidden pick, private distinction.

**Figure's name** (`draft_data.beats[<id>].figures`, `Distinction.asks_figure_name`, #4872):
The name a player gives the person a person card is about (Rival, Capable Mentor); in the
pick's notes and on a granted NPC asset. _Avoid_: NPC name field, companion.

**Term** (`OffersResponse.terms`, `VisibleOffer.effects`, #4872):
A lever named on a card's mechanics line, with its definition read from the row that owns
it: `Trait.description`, `Aspect.description` or `ModifierTarget.description`.
_Avoid_: tooltip text (a copy key), glossary entry.

**Kept beat** (`Beginnings.beat_mode = ONE_KEPT`, #4124; retired #4830, the Sleeper strikes every stage instead):
The one beat a blank-slate Beginning (the Sleeper) takes by itself; every other beat
stands unknown and nothing is addable. _Avoid_: forced beat, default beat.

**Told background** (`Profile.background`, #1270, #4124):
The prose a face presents, drafted from the Upbringing answers and the beats and edited
freely; public by design, one per face. The beats are the true life and are private.
_Avoid_: bio, backstory flag, public beats.

**Maturation floor** (`CharacterSheet.maturation_floor`, #4124):
The matured years a character arrived with; milestones at or below it never bank.
_Avoid_: starting milestones, CG bank.

**Final Touches chapter** (`OfferChapter.FINAL_TOUCHES`, #4846):
The offers chapter whose lines a held card unlocks, by the chapter rule of 2026-10-29:
optional, each answerable or skippable, hidden when nothing is unlocked. Its one opener is
the **unlocking card** (`DistinctionOffer.unlocked_by`). _Avoid_: card-gated offers (the
mechanism, not the name), Final Touches stage (the stage holds more than this chapter),
unlock requirement.

**Final Touches prompt** (`Distinction.final_touches_prompt`, `FinalTouchesPrompt`, #4846):
The optional question a card asks at Final Touches; `crime` is Jailbird's, answered in
`draft_data.crime` and written as a staff-only crime note (`justice.CharacterCrimeNote`) at
finalize. A grant sidecar raises its own prompt without the staff field (#4852):
`prestige_story` (a prestige grant; the answer in `draft_data.prestige_stories` becomes the
pick's notes), `organization` (an organization grant with no fixed organization; the pick
in `draft_data.organizations` from the **organization choices**, the realm's organizations
that admit player characters), `path_aspect` (a path aspect grant; nothing to answer, the
line names the Path's stronger Aspect), and since #4856 `officially_dead` (a worn persona
grant: the door of #4396, shown to no other draft), `alter_ego` (a hidden persona grant;
`draft_data.alter_ego`, the door's shape) and `tie` (an organization tie; `draft_data.ties`
names one of the ask's `choices` and a `TieKind`, membership or renown). `final_touches_cards`
lists the card behind each ask, with its `choices` for the organization asks. _Avoid_: lingering question, door (the officially-dead door is a different shape),
card effect, grant prompt field (a grant's prompt is derived, never authored).

**Suggested life** (`OfferFirstLook.preselected`, #4865, slice 7 of #4813):
The cards a beginning starts a newcomer with (ruled 2026-10-19; net zero per beginning, 2026-10-25): its first-look pins flagged `preselected`, loaded as ordinary priced picks by `offers.load_default_life` when the life first opens for that beginning, every card changeable. One starred card per one-of beat stands (the first by the grid's order); an age-scaled beat takes as many as the age's points buy. Authored on the Beginning admin's "Suggested life" inline or by the paste's leading star (`*Reavers`).
_Avoid_: default life (the plan's working name; the player-facing word is "suggested"), preset, template life, starter pack.

**Start blank** (`offers.clear_life`, the draft's `clear-life` action, #4865):
The leaf's door out of the suggested life: drops the life's picks and beat states, keeps every other chapter's pick and the `life_loaded_for` stamp, so the suggested life does not return over an emptied one.
_Avoid_: reset (the whole draft is not reset), clear all.
