# Missions glossary

**Mission**:
An authored branching graph of decision nodes a character undertakes, drawn from a `MissionTemplate` and run as a `MissionInstance` (the live run, whose state is just its current node plus durable snapshots and recorded deeds — no state blob). The umbrella term for the system; "Mission" names the concept, with template-vs-instance distinguishing the static graph from a play-through.
_Avoid_: quest, job, task.

**MissionTemplate**:
An authored mission: the static node graph (entered at its single entry node) plus its availability metadata — level band, risk tier, draw weight, arc scope, and visibility. The reusable definition that `MissionInstance` runs.
_Avoid_: mission definition, quest template.

**Mission Deed**:
A `MissionDeedRecord` — one recorded consequential act taken within a mission run, attributed to the acting participant's character (moral and narrative consequence follows the actor). Its structured payouts are stored as child `MissionDeedRewardLine` rows rather than a dict.
_Avoid_: deed log, mission action, consequence record.
