# ADR-0272: Family entry is a staff-authored Vacancy with two importance axes; players never create authority

**Status:** Accepted (#3648, 2026-09-05, TehomCD ruling). Related ADR-0268, ADR-0269, ADR-0209, ADR-0238.

**Context.** #3617 left family-level answers on the character and gave a character no
recorded place in a staff family. Restructuring the Lineage step raised what a
"position" in a family is, whether players may define one, and where a powerless
family's identity lives.

**Decision.** A Family Template (`HouseTemplate`, generalized past nobles) is the type
an Upbringing's name path builds from; the named family materializes an Organization
through the noble builder with `influence = 0` and no review, and its aspect answers,
features and fealty to a served house live on that org (ADR-0268). Entry into a
staff-minted family is a **Vacancy** on the family's org: staff author `importance`
(how much the family cares) and `presumed_importance` (what outsiders assume) as
descriptors with no consumer yet, price it flat plus per-influence times the
Vacancy's family's influence (extending ADR-0269 to a second consumer), and set a
capacity where blank means a standing vacancy. Kin versus retainer is derived from
whether the Vacancy links a `KinSlotPool` or an appable `Kinsperson`. One Vacancy per
character at CG. Vacancies are credited and authored in the database but are not
corpus rows: they belong to one installation's family. Openness is enforced only at
finalize, never at draft-time validation: `get_lineage_errors` calls
`reachable_vacancies(draft, require_open=False)` when checking a previously selected
Vacancy is still reachable, so a Vacancy that fills between pick and approval degrades
gracefully through `take_vacancy`'s `VacancyExhaustedError` at finalize instead of
blocking `require_draft_complete`'s re-validation on approval. A malformed
`HouseTemplate.name_pattern` (a staff authoring error, not a player mistake) is a soft
validation error ("tell staff"), never an uncaught `re.error`.

**Rejected.** A free rank pick (lets a player self-anoint). Vacancies as Upbringing
choices (no per-family list, no capacity). Aspects on `Family` (two homes for one
fact; contradicts ADR-0268). Generalizing holdings now (#3618 owns it). Names
Position, Appointment, Seat, Station, Role, Standing, Regard (each already means
something else here).
