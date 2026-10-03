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

**Kept beat** (`Beginnings.beat_mode = ONE_KEPT`, #4124):
The one beat a blank-slate Beginning (the Sleeper) takes by itself; every other beat
stands unknown and nothing is addable. _Avoid_: forced beat, default beat.

**Told background** (`Profile.background`, #1270, #4124):
The prose a face presents, drafted from the Upbringing answers and the beats and edited
freely; public by design, one per face. The beats are the true life and are private.
_Avoid_: bio, backstory flag, public beats.

**Maturation floor** (`CharacterSheet.maturation_floor`, #4124):
The matured years a character arrived with; milestones at or below it never bank.
_Avoid_: starting milestones, CG bank.
