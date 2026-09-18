# character_sheets glossary

Domain-local vocabulary. Cross-cutting terms live in the root
`AGENT_GLOSSARY_MAP.md`.

## Age axes (#2756, ADR-0172)

- **Chronological age** — years since birth on Arx's timeline; derived from
  `CharacterSheet.ic_birth_year` against `get_ic_now()`, never stored. Null
  birth year = unknowable ("Unknown" to every viewer, the player included).
  _Avoid_: real age, true age.
- **Matured years** — years of aging actually lived forward; the maturation
  meter that funds Maturation Points. Advanced by the birthday tick; paused by
  `aging_paused`; reduced only by true age-reversal magic.
- **Withered years** — years stacked on by curses/vitality drains. Count toward
  biological age (decline, death, looks) but never earn milestones; restoration
  magic may strip them. Pure detriment.
- **Biological age** — matured + withered years: how far the body has traveled
  toward death. What old-age decline reads. _Avoid_: physical age.
- **Apparent age** — the age the world reads; equals biological age. Cosmetic
  overrides (glamours, guises, shapechange) are an appearance-layer concern and
  deliberately free — they never touch the stored axes. _Avoid_: display age.
- **Celebrated birthday / waking day** — `birthday_month`/`birthday_day`, the
  date celebrated each IC year (a Sleeper celebrates the day they woke;
  whether it is their true birth date is unknowable). Surfaces in the Town
  Crier birthday digest (`tidings.FeedItemKind.BIRTHDAY`).
- **Maturation Point** — deterministic stat point earned at matured-year
  milestones (21, 24, 27, …); spends live in `progression.MaturationSpend`,
  active iff `milestone_year <= matured_years`. _Avoid_: birthday point, age
  point.
- **Frailty** — the old-age condition (vitals): severity counts accumulated
  decline and reduces max health −1 per point via the `max_health`
  ModifierTarget. Crossing the aging floor opens the **dying window**
  (`CharacterVitals.aging_death_ic_deadline`).
- **Heritage first appearance** — `Heritage.first_appeared_ic` (#3663): the IC
  date the first of a heritage were born; nobody of that heritage can be older
  than the whole IC years elapsed since. Read only by CG's `age_bounds` (the
  ceiling a draft may pick, floor 18); never touches a finalized sheet's axes.
  The first Misbegotten were born in 980 AS. _Avoid_: heritage start date,
  age cap field.

## Profile Beginnings (#3775, ADR-0303)

- **Profile Beginnings**: `ProfileBeginnings`, every origin a character holds, with its
  `source` (`character_creation`, written once by the wizard at where play began;
  `recovered_memory`, a Sleeper remembering the homeland they were taken from;
  `past_life`, a reincarnation remembering a former life). The set only grows - a
  character keeps every origin it has ever held, and adding a row through the Profile
  admin grants that origin's codex entries to the one character. `Profile.beginnings` is
  the M2M this row is the through table of; `CharacterSheet.beginnings` forwards to it
  read-only. _Avoid_: second beginnings, origin slot.

## The Actor's Sheet (#3621, ADR-0279)

- **Actor's Sheet** — the out-of-character half of Chapter 10: three questions about what
  the character does ("What would you never do?", "What would you protect at all costs?",
  "What are you deathly afraid of?"), stored as `Profile.never_do` / `protect` / `fear`,
  versioned prose like `background`, public on the sheet; plus the goals and the enemy.
  Replaces the free-text personality field. _Avoid_: personality, traits, character sheet
  (that is the whole `CharacterSheet`).
- **Enemy** — `CharacterEnemy`: who wants the character to fail, a **person** rated by
  power (`EnemyPowerTier`, Quiescent below Prospect) or a **group** by reach
  (`societies.EnemyReach`, from its `OrganizationType`), at a **degree** (`EnemyDegree`:
  annoyed, thwarted, ruined, "will relentlessly try to destroy you"), awarding CG points
  (the price) that the world collects. **Placed** when linked to a real person or group;
  **pending** until staff link a free-written one. The row is owner, staff and assigned-GM
  reading; the sheet shows the **public line**. _Avoid_: antagonist, nemesis (a nemesis is
  the destroy degree), rival (relationships' Rivalry track), obstacle.
- **Reach** — how far a group can reach a character who made an enemy of it: a household,
  a house or company, a society or church, a realm. Set once per `OrganizationType`; a
  Beginning's enemy offer may override it for a group that cannot reach where the character
  plays. _Avoid_: scope, scale (the general word for either axis).

## Mood (#2994)

- **Mood** — a character's declared internal emotional state (`feel <state>`,
  `SetMoodAction`, `CharacterSheet.current_mood → MoodOption`). INTERNAL and
  SILENT by design: setting one never echoes to the room, is never rendered
  into look/appearance text, and carries no mechanical effect. Sticky until
  re-declared or cleared (`feel` with no argument) — mirrors
  `current_language`'s sticky-nullable-FK shape exactly, but lives on
  `CharacterSheet` (not `Persona`) since a mask doesn't change how the person
  underneath feels. Own mood is always visible to self and staff (owner/staff
  gate on `CharacterSheetSerializer`'s identity section); any other viewer
  learns it only through the earned `SenseMoodAction` (`sense_mood`, gated on
  an Empathy skill specialization + `perform_check` — never ambient). No
  collision with `StanceArchetype` (proclamations, ADR-0178) or `NpcRegard`'s
  declared stance (ADR-0085) — both are directed, numeric-judgment concepts;
  Mood has no target and no numeric value. `MoodOption` is a curated,
  content-authored lookup (ships empty in code; seeded via the lore repo's
  content round trip). _Avoid_: mood/stance/disposition as a synonym for
  `StanceArchetype` or `NpcRegard`'s declared stance — those are different,
  already-claimed concepts (see their own ADRs).

## The Reference Sheet (#3898)

- **Plate** — the head of the web character sheet: the art, the name with its
  titles, the concept, the quote, two glance lines and the looks strip. Painted
  in night literals in both themes because it is the cover of the page. Nothing
  mechanical belongs on it. _Avoid_: header, hero, banner.
- **Look** — one image of a character, tagged with the `MoodOption` it shows
  (`TenureMedia.look`). The character WEARS one, which is the roster entry's
  profile picture; the rest sit beside it in the strip. Tagging an image says
  what the picture shows, never what the character feels — a look is outward and
  public, [Mood](#mood) is inward and silent, and they share `MoodOption` only so
  that "which mood" has one vocabulary. _Avoid_: expression, pose, portrait
  (a portrait is any image; a look is a tagged one).
- **Plate ink** — which of four grounds a player's plate is printed on
  (`CharacterSheet.plate_ink`, `PlateInk`). OOC chrome, set in settings, and the
  only part of the sheet's appearance a player chooses. The page below the plate
  stays on Arx paper whichever is picked. _Avoid_: theme, skin, realm colour (a
  realm ink is a different, world-facing concept).
- **Section** — one of the sheet's eight pages (Sheet, Physical, Ties,
  Distinctions, Magic, and the owner-only Knowledge, Estate, Growth). _Avoid_:
  tab — the sixteen-tab strip is what #3898 replaced, and the word carries it.
- **Estate** — the owner-only section holding a character's purse, what they
  carry, where they live, the land their organizations hold, what they have
  promised and whether the law wants them. Named Estate because "holdings"
  reads as fiefs and this is one person's money, things, roof and record;
  Estate is the word the will copy inside it already uses (#3901). _Avoid_:
  Holdings, Possessions, Property (Property is one block inside it).
- **Band** — a full-width folding block below the sheet's columns, holding
  material that is gated or simply tall (goals and guidelines, abilities). A
  band a viewer may not read is absent, never empty.
- **Entry** — one hairline-separated row in the sheet's index voice: a name, an
  optional tag or two, a gloss beneath. The sheet's unit of listing, and what a
  card used to be everywhere the sheet took a panel over. _Avoid_: card, tile,
  row (a row is a table's).
- **Quiet door** — a link the sheet offers without dressing it as a button
  ("Change outfit", "Commend"). Reads as text until the reader is on it.
  _Avoid_: action button, CTA.
- **Plateau** — the one framed area the sheet draws, for something DRAWN rather
  than written (the kin graph). A drawing needs an edge; prose does not.
  _Avoid_: card, panel, box.
- **Worn** — what a character has on, as the #2985 layer walk says an onlooker
  would see it (`worn` on the sheet payload). Worn things are visible things, so
  this is not gated by a visibility tier; only a COVERED piece is owner-only, and
  it carries `is_hidden` so the sheet can say it is there and unseen. _Avoid_:
  equipment, inventory (those are everything they hold, not what shows).
