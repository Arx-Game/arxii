# Character Creation Frontend

This module provides the staged character creation UI flow.

## Structure

```
character-creation/
├── index.ts                 # Public exports
├── types.ts                 # TypeScript type definitions
├── constants.ts             # MAGIC_SKILL_CATEGORY: Magic skills are spent from the Gift
│                              #   stage's magical training (read-only group in SkillsSection,
│                              #   #4457, #4659), never bought with skill points
│                              #   `NOT_YET_IMPLEMENTED`: the tag on a path, tradition or
│                              #   beginning whose row says `not_yet_implemented` (#5197).
│                              #   The choice stays listed and selectable; the server derives
│                              #   the flag, so no frontend change removes the tag. PathStage
│                              #   asks `/paths/?beginning_id=`, TraditionPicker
│                              #   `/traditions/?beginning_id=&path_id=`
├── api.ts                   # API fetch functions using apiFetch
├── queries.ts               # React Query hooks
├── cg.css                   # Scoped under `.interview`; realm is an ink, paper
│                              #   pinned to Arx (#3540)
├── CharacterCreationPage.tsx # Main page component
├── folio/                   # Folio chassis primitives (#3540), realm-agnostic
│   ├── index.ts             # Barrel re-export
│   ├── ContentsRail.tsx     # Chapter table of contents; replaces StageStepper. What a row
│   │                        #   says (#5199, owner rulings 2026-11-18): a stage the draft has
│   │                        #   not been opened on is its name alone; an opened stage shows
│   │                        #   the first thing it still asks; a finished stage is marked
│   │                        #   complete; a stage that asks nothing reads "optional" and is
│   │                        #   never marked complete. Which stages are opened and which are
│   │                        #   optional come from the server (`visited_stages`,
│   │                        #   `optional_stages` on the draft); the stage the draft stands
│   │                        #   on always counts as opened
│   ├── PageTurn.tsx         # Back/next doors between chapters, the same button (owner
│   │                        #   ruling 2026-11-16, #5146: Back is not an italic link);
│   │                        #   `between` is a stage's own door drawn between the two
│   ├── NightPlate.tsx       # Full-bleed night moment (arrival, submission)
│   ├── ChapterLeaf.tsx      # Wraps a stage's old internals in the leaf frame; `aside` is
│   │                        #   the right-hand panel; `railSlot` lets the leaf take the
│   │                        #   whole room and keeps a slot at the foot of that panel
│   ├── chapterRail.ts       # `useChapterRail()`: the slot at the foot of the right-hand
│   │                        #   panel that a stage's own list portals into (#5148)
│   ├── RecordRail.tsx       # Marginalia: the "CG selections" rows + a Note aside. The rows
│   │                        #   come from `../cgRecord.ts` (#5199): `cgRecord(draft)` gives
│   │                        #   `head` (Name, Origin, Beginning, Species, Gender, Family or
│   │                        #   Surname, Path, Tradition) and `points`, and a stage writes
│   │                        #   `[...record.head, ...its own rows, record.points]`. No stage
│   │                        #   writes the shared rows itself. The surname is the server's
│   │                        #   (`draft.surname`); on a route with no family the row is
│   │                        #   "Surname" and holds the drawn card's. The points row
│   │                        #   is marked `points` and takes the page's hover text
│   │                        #   on what becomes of unspent points (#5201,
│   │                        #   `pointsHint.ts`: `PointsHint` is provided once by
│   │                        #   CharacterCreationPage from the active budget's rate)
│   ├── Entry.tsx            # EntryList/Entry/EntryDoors: choosable record entries (`tag`
│   │                        #   is optional and marks the exception only, #5207: no
│   │                        #   "Available" on every row; an
│   │                        #   optional `tags` list prints extra `.tag`s beside `tag`). Since
│   │                        #   #4022 the name row carries a square Select mark (Selected
│   │                        #   once chosen, a second press clears; never toggles the
│   │                        #   disclosure) and a chosen row is tinted in the realm accent;
│   │                        #   the foot keeps one door, Select before and Clear after
│   ├── InstrumentFrame.tsx  # InstrumentGroup/StatRow: labeled stat instruments
│   ├── ChoiceRow.tsx        # Segmented choice: a few named options, one pressed (#3630)
│   ├── SwatchRow.tsx        # A colour choice (#5241): one round swatch per option in the
│   │                        #   option's own colour (`--swatch`, checked as #rrggbb before
│   │                        #   it goes into a style), named on hover and to a screen
│   │                        #   reader; an option with no colour is striped (`no-hue`), one
│   │                        #   outside the ordinary list dashed (`beyond`); `onPreview`
│   │                        #   hands the caller the name under the pointer or the focus
│   ├── Field.tsx            # Inscription label over a serif control on a hairline (#3630);
│   │                        #   `className` is a width class for a field in a `.field-row`
│   │                        #   (short fields side by side, #5241), e.g. `narrow`
│   ├── Paragraphs.tsx       # Blank-line-separated prose split into <p> tags (#3630)
│   ├── CodexWord.tsx        # In-world term linked via CodexTerm when a codex entry exists
│   ├── CodexLine.tsx        # "Codex: {name}" ledger line in an entry body (solid link; an
│   │                        #   optional `note` such as a cost reads after it); nothing without either
│   └── ConfirmDialog.tsx    # Native <dialog> confirm for record-clearing choices
└── components/
    ├── index.ts             # Component exports
    ├── OriginStage.tsx      # Stage 1: Area selection; since #4874 the first name is asked
    │                        #   here too (a Field above the realms, boxed while empty, saved
    │                        #   on blur by itself, listed first in the rail), so the life
    │                        #   reads the name; the letters-only rule shows only under a
    │                        #   refused name, and a refused name is not saved
    ├── HeritageStage.tsx    # Stage 2: beginnings (station on the closed row, cost on the
    │                        #   codex line), species, gender
    ├── LineageStage.tsx     # Stage 3: the beginning's route (#3617; the Upbringing pick
    │                        #   retired in #4395, the route comes with the beginning),
    │                        #   family selection, the life grids (no spouse, child or
    │                        #   twin: those come after creation, ADR-5102-A); keeps
    │                        #   InventedParentsCard, FamilyNamePreview, KinSlotPicker,
    │                        #   TarotNamingRitual, TarotCardItem, FamilyCard (exported
    │                        #   for lineage/). TarotNamingRitual keeps its 78 cards
    │                        #   folded behind "Choose a card" (#5201): the surname, the
    │                        #   draw and the orientation switch are all that show until
    │                        #   that door is opened. The stage ends on the life; the
    │                        #   LineageRecord box is removed (#5201). KinSlotPicker (#5130) is the open seats
    │                        #   of the claimed family and the only way into it: no free
    │                        #   card; a seat reads its relation to the head of the house
    │                        #   (`head_relation` + the response's `head_name`), then its
    │                        #   description; a changeable name carries an asterisk, a
    │                        #   fixed one nothing; a second press clears the pick.
    │                        #   HouseFoundingPanel retired (#3983 Plan B
    │                        #   Task 6) — claim-path house founding is
    │                        #   `almanach/founder/FounderAlmanach.tsx`, mounted from
    │                        #   `FamilyPathSection.tsx`.
    ├── PathStage.tsx        # Stage 5: Path selection
    ├── SkillsSection.tsx    # Skill point allocation, mounted inside AttributesStage
    ├── AttributesStage.tsx  # Stage 7: Attributes & Skills (mounts SkillsSection). A draft
    │                        #   with no saved statistics has the spread on screen saved when
    │                        #   the stage opens, once (#5198), so the even spread needs no click.
    │                        #   Labels as the owner ruled (#5223): the Statistics frame reads
    │                        #   "Min 10, Max 50", the four categories carry no gloss, a
    │                        #   statistic's name shows what it governs on hover (`whyTitle`)
    │                        #   and, pressed, in the side panel, never under its row; the
    │                        #   Skills frame reads "Specialization at N in parent skill." and
    │                        #   a bare spent/total, and the side panel has a "Skills" row
    │                        #   under "Statistics" (SkillsSection reports through
    │                        #   `onPointsChange`). The side panel's row is "Beginning", singular
    ├── GiftStage.tsx        # Stage 6 (Gift): vertical funnel — Tradition → Gift →
    │                        #   [magical training, #4659] → Techniques → Gift Resonance
    │                        #   (a feeling, a side and a balance, #5231: `StrengthStep`
    │                        #   asks which Primal feeling gives strength, whether helping
    │                        #   or hurting others does too and which resonance on that
    │                        #   side, then the split of the server's
    │                        #   `resonance_creation_points` with the aura drawn beside it;
    │                        #   saves `draft_data.gift_resonance_weights` as one whole list
    │                        #   obeying the server's rule; the whole step is drawn from the
    │                        #   start (the aura is grey for a feeling not yet picked and the
    │                        #   slider is disabled), and a stored list that breaks the rule
    │                        #   shows nothing chosen so the player picks again;
    │                        #   `resonanceWeights.ts` holds the pure helpers)
    │                        #   → Anima Check, plus an
    │                        #   always-visible Motif textarea and the guided Glimpse
    │                        #   flow (#2426 Task 10; Glimpse redesign #2427)
    ├── AppearanceStage.tsx  # Stage 8: Appearance, in compact controls (#5241, owner
    │                        #   rulings 2026-11-21). Age and the birthday share a line: the
    │                        #   birthday is two numbers, month then day, saved once both are
    │                        #   typed and read back as "Day 14 of <the game's month name>".
    │                        #   Height band and build are dropdowns on one line with the
    │                        #   inches; the chosen band's own authored `cg_hint` column
    │                        #   (forms.HeightBand, #3675 fix round 1) reads under it, never
    │                        #   a name match against a literal band name. No control on the
    │                        #   stage is a row of a button per option. Then this chapter's
    │                        #   own offered distinctions (ChapterOffers chapter="appearance",
    │                        #   #3675 Task 15), one block per authored section. Then the
    │                        #   features, two across (`.feature-grid`), each an
    │                        #   `appearance/TraitBlock`. The heading and the side panel's
    │                        #   "Feature points" row say how many of the free ten are spent
    │                        #   (from `useShownPicks(draft).featureSpent`, so they move with
    │                        #   a click); neither shows when staff have authored no quality
    ├── appearance/
    │   └── TraitBlock.tsx   # One feature: a `SwatchRow` for a colour (`trait_type`
    │                        #   "color"; the chosen colour's name beside the trait's name),
    │                        #   a dropdown for anything else; under it the qualities line
    │                        #   (`offers/FeatureDistinctions`), and the "Describe it" field
    │                        #   once the feature holds a tier. Options outside the ordinary
    │                        #   list are a dashed swatch or a "Distinctive" group
    ├── MarkingsEditor.tsx   # Markings (#2985): the form asks name, kind and region on one
    │                        #   line, kind and region as dropdowns (#5241); each saved
    │                        #   marking carries the qualities line. Removing a marking
    │                        #   also refetches the draft's picks, the draft and its CG
    │                        #   points: the server drops the marking's qualities in the
    │                        #   same request, and a stale list was sent again with the
    │                        #   next quality clicked and refused
    ├── IdentityStage.tsx    # Stage 9: Identity (concept, quote, worship); the name is a
    │                        #   read-only line since #4874, asked on Origin. The Background
    │                        #   is Final Touches' (#5178); this stage neither reads nor
    │                        #   saves it. Between the quote and worship, the Personality
    │                        #   block (#5255, owner ruling 2026-11-21): an h2 (copy
    │                        #   `identity_personality_heading`) over `ChapterOffers
    │                        #   chapter="identity"` as the life page's cards, two across
    │                        #   (`pair`), signed prices, four at rest and the rest under
    │                        #   "See N more"; once staff give the lines headings every
    │                        #   card shows under its heading and nothing folds. Absent
    │                        #   when no card is placed. The side panel's points line
    │                        #   reads `useShownPicks`, so it moves with a click
    ├── FinalTouchesStage.tsx # Stage 10: the Actor's Sheet (#3621): three questions,
    │                        #   numbered goals by horizon, the priced enemy, The Introductions.
    │                        #   The enemy section, its side-panel row and its note render
    │                        #   only when a held card asks `enemy` (#5255:
    │                        #   draft.final_touches_cards), headed by that card's name;
    │                        #   "Who wants you to fail" is printed nowhere and the copy key
    │                        #   `finaltouches_enemy_heading` is not read. An enemy card by
    │                        #   itself does not open the card-unlocked section.
    │                        #   After the enemy and before the faces' doors, the Background
    │                        #   (#5178, owner ruling 2026-11-17: one box for the character's
    │                        #   history, no text per life stage): an h2 "Background" and a
    │                        #   `textarea.background-text` named by it, 4000 characters,
    │                        #   an italic placeholder as its only explanation (copy
    │                        #   `finaltouches_background_heading` /
    │                        #   `finaltouches_background_placeholder`), saved in the
    │                        #   stage's one PATCH as draft_data.background and quoted on
    │                        #   Review. A second face writes its own in its door.
    │                        #   Directly under the three questions mounts this chapter's own
    │                        #   offered distinctions (ChapterOffers chapter="actors_sheet",
    │                        #   #3675 Task 15), the personality-flavored ones each prompt
    │                        #   answers. Between the questions and the goals, the
    │                        #   card-unlocked chapter (#4846, slice 5 of #4813): the lines
    │                        #   a held card unlocks (ChapterOffers chapter="final_touches")
    │                        #   and the prompt a held card asks (draft.final_touches_prompts;
    │                        #   `crime` is Jailbird's: a select over draft.crime_kinds and a
    │                        #   500-character line, saved as draft_data.crime in the stage's
    │                        #   one PATCH, null when no kind is picked). The asks the grant
    │                        #   sidecars raise (#4852, slice 6 of #4813: draft.final_touches_cards)
    │                        #   each get a block under the card's name: a prestige card's story
    │                        #   (500 characters, draft_data.prestige_stories keyed by card id,
    │                        #   a blank one dropped), the organization a card seats you in (a
    │                        #   select over draft.organization_choices with "None" first,
    │                        #   draft_data.organizations, null for None), Capable Mentor's line
    │                        #   naming the Path's stronger Aspect from the ask's detail (nothing
    │                        #   to answer), and a card's organization tie (#4856: a select over
    │                        #   the ask's choices with "None" first, then the kind as a
    │                        #   ChoiceRow, membership or renown; draft_data.ties keyed by card
    │                        #   id, null for None). The section is absent when no held card
    │                        #   unlocks or asks anything. The Officially dead door (#4396)
    │                        #   renders only when the prompts include officially_dead (#4856:
    │                        #   Presumed Dead's card), and a second door of the same shape,
    │                        #   "A second face", when they include alter_ego (saved as
    │                        #   draft_data.alter_ego, null when skipped); both share FaceForm.
    ├── ReviewStage.tsx      # Stage 11: Review and submit
    ├── FinalizeForTableDialog.tsx # Player-GM direct-to-roster flow from ReviewStage (#3268)
    ├── TraditionPicker.tsx  # Traditions as entries — mounted inside gift/TraditionStep; each
    │                        #   entry names the affinity skills it teaches ("Teaches Reflection
    │                        #   and Heroism", from `taught_skill_names`, #5326)
    ├── PerspectivesPanel.tsx # "On {subject}" shop-window opinions; renders as margin
    │                        #   notes in HeritageStage and inside the chosen tradition's
    │                        #   entry in TraditionPicker (#3281, #3630)
    ├── gift/                # GiftStage funnel steps (#2426 Task 10)
    │   ├── TraditionStep.tsx    # Wraps TraditionPicker
    │   ├── StrengthStep.tsx     # The Resonance step body (#5231): the feeling cards, the
    │   │                        #   three answers about others, the second cards, and the
    │   │                        #   balance slider beside the night plate holding
    │   │                        #   `AuraSwirl` (`@/magic/components`); words from the
    │   │                        #   `gift_strength_*` CG explanation keys; each affinity's
    │   │                        #   staff-written description (`affinities` prop, from
    │   │                        #   `useAffinities`) sits under the question for its
    │   │                        #   cards, nothing while it is blank (#5293)
    │   ├── GiftSelector.tsx     # Gifts as entries (GET .../gifts/?draft_id=); a Gift the
    │   │                        #   Tradition favors is tagged "Teaches well" (#4659)
    │   ├── MagicTrainingBlock.tsx # Body of GiftStage's own "What <Tradition> taught you"
    │   │                        #   funnel step (#4659), after the Resonance step, gated on
    │   │                        #   a Gift and a resonance (its bonuses read both), open
    │   │                        #   until the pool is spent exactly: the breakdown
    │   │                        #   ("<distinction>, rank N" sources, the rank only when
    │   │                        #   `show_rank`; "Fits:" bonuses,
    │   │                        #   total), a "Spend all of it" ledger flagged when under or
    │   │                        #   over, and a StatRow per Magic skill writing
    │   │                        #   draft_data.magic_skills. The step is absent with no
    │   │                        #   training and nothing allocated (`magicTraining.ts`)
    │   ├── StyleStep.tsx        # The fighting style step (#4921), after the Resonance and
    │   │                        #   only for a Tradition that teaches a style (GET
    │   │                        #   .../combat-styles/?draft_id=): each style's defense style,
    │   │                        #   description and an Attacks/Defends profile read in the
    │   │                        #   closed entry (Entry's `profile` slot; the lines in
    │   │                        #   `styleLines.ts`), never its vows; saves
    │   │                        #   selected_combat_style_id. The training step waits on it
    │   ├── TechniqueSelector.tsx # Technique catalog, grouped by category, budget-capped
    │   ├── AnimaCheckStep.tsx   # Anima Check stat/skill pick + ritual name. Each pick is one
    │   │                        #   dropdown in the Field style (#5220, owner ruling 2026-11-20;
    │   │                        #   they were a button per statistic and per skill): the
    │   │                        #   suggested option first, the rest under category headings
    │   │                        #   (`optgroup`), never a Magic skill
    │   ├── GlimpseSection.tsx   # CG state binder for the Glimpse (#2427): draft reads,
    │   │                        #   updateDraft writes (draft_data.glimpse_tag_ids), the
    │   │                        #   isCollapsed deferral affordance, the copy query. Prose
    │   │                        #   stays on GiftStage's register('glimpse_story'). Renders
    │   │                        #   `GlimpseAxes`, not the shared
    │   │                        #   `@/magic/components/glimpse/GlimpseFlow` (#3675 fix
    │   │                        #   round 1: that shared component's shadcn accordion hid
    │   │                        #   two axes at a time; the sheet's live editor still uses
    │   │                        #   it, unchanged)
    │   └── GlimpseAxes.tsx      # CG-only folio-grammar layout for the Glimpse (#3675 fix
    │                            #   round 1): one `.field` per axis, all visible at once.
    │                            #   Since #5191 (owner ruling 2026-11-18) an axis is headed
    │                            #   by its name (an `h3.label`, "Trigger"; copy
    │                            #   `glimpse_axis_<axis>_chip`) with a muted italic `.lead-in`
    │                            #   line under it ("The Circumstances Around Your
    │                            #   Glimpse:"; copy `glimpse_axis_<axis>_lead_in`), and its
    │                            #   tags are the life page's cards, `ul.stances.grid.pair`
    │                            #   of `button.stance`: one width, two across (one on a
    │                            #   phone) because a tag's description is prose that can
    │                            #   run to several sentences, a round mark on an axis
    │                            #   that takes one answer and a square one on an axis that
    │                            #   takes several. Only the latter prints "choose any";
    │                            #   "choose one" is never printed. What a click does to
    │                            #   an axis's picks is `nextAxisSelection`
    │                            #   (`@/magic/components/glimpse/axisSelection.ts`, shared
    │                            #   with the sheet's editor): a tag that stands alone
    │                            #   (`stands_alone`, #5193; Fugue in The Reflection)
    │                            #   replaces the axis's other picks, and picking another
    │                            #   lets it go. The `.picks` pill
    │                            #   buttons, the `glimpse_axis_<axis>_prompt` keys and
    │                            #   `glimpse_choose_one` are retired. One `ChapterOffers`
    │                            #   `.conditional` sub-block PER SELECTED TAG (not per
    │                            #   axis: two tags chosen on one multi-select axis each
    │                            #   get their own heading, matching the demo). No heading
    │                            #   of its own; GiftStage's `section-h` above the mount
    │                            #   carries it. Each sub-block passes ChapterOffers a
    │                            #   headingTag ("optional"); a route-closed distinction is
    │                            #   absent and named nowhere (#4979).
    └── lineage/             # LineageStage subsections (#3617, #3648, #4395)
        ├── (KinRows.tsx retired, #5102) The named parents' fates (#4870) are a select
        │                         #   under each parent's gender in LineageStage
        │                         #   (ParentFateRow; draft_data.line_parent_fate /
        │                         #   other_parent_fate)
        ├── LifeGrids.tsx         # The life in folds (#4874, slice 9 of #4813, built
        │                         #   against the demo): one fold per stage (heading + "N of
        │                         #   M" or Unknown) and one section per beat inside. Every
        │                         #   stage and section is open on arrival and each folds by
        │                         #   itself (owner ruling 2026-11-16, #5160: "everything
        │                         #   should start as expanded"; no one-open-at-a-time). A
        │                         #   closed section reads its answers with signed points or
        │                         #   the prompt with the first name; an open one prints the
        │                         #   prompt in its body only. A section has no Next of
        │                         #   its own (#5201): its fold arrow closes it and the
        │                         #   page's Next is the only Next;
        │                         #   every grid ends on an Amnesiac card (#5102: no cost, not a
        │                         #   distinction, copy life_amnesiac_name/_text) that marks
        │                         #   its own beat unknown; the secret marks under a grid, the Cover story box
        │                         #   on a one-of row (the no-cost card is saved as the cover when
        │                         #   the secret is marked, until a click on another card;
        │                         #   clicking the real pick drops both)
        │                         #   and a cover select on an any row; a figure's name input
        │                         #   on a picked person card; no free-text box about the
        │                         #   life (#5178: the Background Notes of #5160 and the
        │                         #   Recent History box are removed, and their copy keys
        │                         #   are not read; the Background is one box on Final
        │                         #   Touches); the list of choices,
        │                         #   sent to the slot under the chapter's "CG selections"
        │                         #   (#5148). The life ends on its last stage: no count
        │                         #   line and no paragraph of the picks (#5201).
        │                         #   Earlier shape, still true underneath: grids by stage
        │                         #   (#4395, the #4124 beats):
        │                         #   one block per stage the beginning offers (a struck
        │                         #   stage is absent), each beat a `ChapterOffers`
        │                         #   `layout="grid"` of its `backgrounds` offers picked
        │                         #   straight from the cards, the pick line from the
        │                         #   entry's `allowance` (one, N career points on a beat
        │                         #   whose `allowance_is_points` is on (#4829: a ranked
        │                         #   card shows pips, `ChapterOffers` `pointsPicks`), any),
        │                         #   a line of the player's own once a card
        │                         #   is picked. A beginning that
        │                         #   strikes every stage shows its struck_stages_text
        │                         #   where the stages would be and nothing else, with no
        │                         #   footer. Replaces BeatsBlock. The suggested life
        │                         #   (#4867, slice 7 of #4813): once the beats load, an
        │                         #   effect calls useLoadDefaultLife when the draft has a
        │                         #   beginning its draft_data.life_loaded_for stamp does
        │                         #   not name (a ref stops a second call per mount; the
        │                         #   server's stamp is the durable guard). Clearing the
        │                         #   life is LineagePageTurn's door, not a button here
        │                         #   (#5146). Both hooks replace the draft cache and
        │                         #   refetch the distinctions, beats, Backgrounds offers
        │                         #   and CG points.
        ├── LineagePageTurn.tsx   # The foot of the Lineage stage (#5146): PageTurn with
        │                         #   "Restart: Clear All Choices" between Back and Next
        │                         #   (copy `life_restart_label`; the retired key
        │                         #   `beats_start_blank` is not read). It opens a
        │                         #   ConfirmDialog saying what goes and what stays, and
        │                         #   calls useClearLife on confirm; the door is disabled
        │                         #   while a load or a clear of the life is in flight
        │                         #   (`lifeMutationKey`). Mounted by CharacterCreationPage
        ├── UpbringingPrompts.tsx # Route prompts; `scope: 'any'` renders the pick-lists
        │                         #   asked on every path (a general write-in never
        │                         #   renders, #4395), `scope: 'path'` renders below the
        │                         #   family block, scoped to the resolved family path;
        │                         #   write-in ->
        │                         #   draft_data.origin_slots, pick-list ->
        │                         #   draft_data.origin_choices, priced off influence.
        │                         #   Each priced answer prints an `offers X` / `bundles Y`
        │                         #   line off its own `AnswerOffer[]` (#3675 Task 14); the
        │                         #   CHOSEN answer alone, when it carries a CHOICE offer,
        │                         #   mounts a `ChapterOffers` block right after the answers
        │                         #   list (`chapter="lineage"`, filtered to its own choice's
        │                         #   `offer_id`s - never by name/label, #3676 - `className=
        │                         #   "conditional"` merged onto ChapterOffers's own `.field`,
        │                         #   its bundled offers passed through as locked stances). A card
        │                         #   the route closes is absent and named nowhere (#4979).
        ├── FamilyPathSection.tsx # Path picker (when the Upbringing allows more than
        │                         #   one) plus the claim/name/none path UI; renders
        │                         #   FamilyTemplateForm (name path), VacancyPicker
        │                         #   (claim path's kin Vacancies), ServicePanel (any
        │                         #   path's retainer Vacancies), InheritedFactsPanel
        │                         #   (claim path). Reads the Upbringing's `parentage`
        │                         #   (#4024): `unknown` renders only the tarot ritual
        │                         #   (under copy `tarot_no_parents_intro`) and Service,
        │                         #   no family heading or parents card; `adoptive`
        │                         #   heads the section `adoptive_family_heading` and
        │                         #   titles the parents card "Your adoptive parents".
        │                         #   Path labels are "An established family" / "Your
        │                         #   own family" / "No family"; with the first two
        │                         #   offered and none chosen, your own is open by default.
        │                         #   Since #5130 the claim path lists only families with
        │                         #   `has_open_seat` (plus the one the draft holds), shows
        │                         #   the seat picker under the Vacancy heading, and never
        │                         #   the parents card (a seat's parents are staff's)
        ├── FamilyTemplateForm.tsx # Aspect-pick + features form for a Family Template,
        │                         #   used by the name path (#3648); the claim path's
        │                         #   own charter form is
        │                         #   `almanach/founder/FounderHouseChapter.tsx` (#3983
        │                         #   Plan B)
        ├── VacancyPicker.tsx     # Renders reachable Vacancies (description, importance,
        │                         #   presumed importance, price, remaining) for pick
        ├── ServicePanel.tsx      # Retainer Vacancies reachable from this Upbringing,
        │                         #   grouped by house, shown on any resolved path
        └── InheritedFactsPanel.tsx # Read-only aspects/features/liege facet panel for a
                                  #   claimed staff family (#3648)
```

## ChapterOffers, the life page's props (#4874)

`ChapterOffers` (`components/offers/`) grew five props for the life page and keeps every
default for the other chapters. A `layout="grid"` card (the life page's only layout) reads
the distinction's description under its name, not the offer's `player_line` (#5099).
`groupBy` splits a grid under `.group-h` headings
("Group (count)", the ungrouped cards last); `pricing="signed"` prints a grid card's price
as a bare `−N`/`+N` in its bottom-left corner and nothing on a free card; `terms` builds the
mechanics line from `offer.effects` with each term a `.term` role-button (the card is a
button, so no nested button) that shows one `.popover` through a portal to `body` with the
definition from the response's `terms`, while the pointer or the keyboard focus is on it;
a click or tap pins it open, and Escape, a scroll or any other click closes it (#5148). A
term whose definition is blank is plain text with no underline; `interceptPick` runs before a click
changes a pick and `coverOfferId` draws that card dashed (the cover flow);
`secretOfferIds`/`wordSecret`/`wordCover` label the secret pick and the cover on the cards.
`pair` (#5255) puts a grid two across in the reading column (`.stances.grid.pair`, the
Glimpse's rule) with four cards at rest where the others show three, and a grid folded
under "See N more" keeps its cards; the Identity
stage's Personality block uses both.

## A card click shows at once (#5134)

`useSyncDistinctions` (`@/hooks/useDistinctions`) saves the draft's whole pick list and
returns the mutation plus `pendingEntries`: the picks a save in flight is writing for that
draft, from this grid or any other on the page (every instance shares one mutation key;
`usePendingSync` reads it), null when none is. While it is set, `ChapterOffers` reads a
card's rank from it, so the clicked card is picked and an exclusive sibling let go before
the server answers; a card held some other way than by choice (bundled, carried) is in no
save and keeps its rank. Every grid's cards and the schooling stances are disabled until
the save answers: a second save would be built from the list the first is replacing. The
save's answer is put in the draft-distinctions cache as it stands, with no second request;
the draft, the purse and the offers are still refetched.

## The points move with the click (#5141)

On a page that has distinction cards, anything that prints the draft's CG points or lists
its picks reads `useShownPicks(draft)` (`useShownPicks.ts`), never `draft.cg_points_spent`
or the saved list directly: the life page's ledger, the Lineage stage's "CG points" row,
the Gift summary. It
returns `picks`, `spent` and `remaining`. With no save in flight those are the saved list
and the server's own totals. With one, `shownPicks` (`offers/syncHelpers.ts`) lays the
save's rows over the saved list (a pick left out is let go, a changed rank is re-priced
from the price the server charged per rank, a new pick is priced from its cached offer) and
the totals are re-priced: the draft's total, less the prices in `draft_data.distinctions`
(the list the server added its total up from, in the same response), plus the prices in
the list shown. When the save answers, `useSyncDistinctions` writes its list and the
re-priced totals into the cached draft at once; the draft fetch that follows replaces
them with the server's figures. A failed save shows the old totals again. A test that
mocks `@/hooks/useDistinctions` and renders one of these must give the mock a
`usePendingSync`.

The life page prints one points line, the "CG points: N of M spent" row of the panel
every stage shows (#5148); the ledger box and its Starting, Spent, Gained and Remaining
lines are gone.

## The spread follows the window (#5144)

`.interview-grid` runs the width of the window up to 150rem. The contents rail is its left
column on every stage, and the chapter's own rail is the last column of `.chapter`, so the
two rails stand at the same two edges whatever the stage holds.

- A stage's rail is its `aside`: the "CG selections" record (`RecordRail`) and the
  stage's notes. Every stage shows the same record (owner ruling 2026-11-16, #5148:
  stage 3 "should appear identical to the other stages, and then just have the choices
  under it"). A stage that needs a list of its own in the panel does not replace the
  record: it gives `ChapterLeaf` `railSlot`, which keeps an empty `.rail-slot` at the foot
  of the `aside`, and a component deep inside the stage reads `useChapterRail()` and
  portals its list into the element it returns (null where there is no slot, and the list
  then renders where it is written). The life page's choices do this.
- A `railSlot` leaf (`.chapter-grids`) takes all the room; its grids widen by container
  query and its prose keeps 68ch. Every other leaf keeps a 38rem reading column midway
  between the rails. To let a stage use the width, give it a layout that does (columns of
  entries, statistics side by side) and lift its cap; do not stretch a single column,
  which puts a row's name a screen-width from its controls.
- The life's cards follow the life's own width, not the window's (`.leafwrap > .life` is
  a container): one across under 30rem of life, two from 30rem, three from 46rem and more
  above (#5200; they were two across at any width under 46rem, and on a phone a card's
  name ran out of its box and the page scrolled sideways). A card's text column is
  `minmax(0, 1fr)` and its name wraps anywhere, so a long name cannot push a card past
  its cell at any width.
- Under 74rem of window every stage's panel drops under the leaf, the life page's too.
  From 74rem the panel is sticky; a reading stage lets it scroll away in a short window
  (under 52rem tall), a `railSlot` stage keeps it in view at any height, because the
  life page is long and its points line has to stay beside the cards being clicked.

## An element drawn through a portal is outside `.interview` (#5148)

Every rule in `cg.css` is written `.interview <selector>`, a descendant of the page's
root. An element rendered with `createPortal(..., document.body)` is not a descendant of
that root, so none of those rules reach it. The term definition box shipped that way in
#4874 and was a blank page-high sheet in the wrong place until #5148: its markup and
class names were right and no rule applied. Such an element carries the root class
itself (`className="interview popover"`, for the inks) and its rules name both classes on
the one element (`.interview.popover`), taking back what the root rule adds (the page's
`min-height`). `__tests__/portaledStyles.test.ts` holds this for every such element, and
the `portaled-style-reach-reviewer` agent reads a diff for the shape. Evidence for a
styled element is its computed style and its box in a browser, never its class name.

## Feature qualities and the free points (#3739, #5241)

`offers/FeatureDistinctions` is one feature's qualities (Alluring, Menacing, Majestic: the
chapter's `taken_per_feature` offers) on one thin line, each tier a round button; it mounts
once per trait and once per marking. A click sets that tier, and a click on the top tier
held takes it off; there is no step before the tiers (ADR-5241). It reads a tier from the
save in flight (`pendingEntries`) and takes no second click until that save answers.
`onClosed` fires when a click takes the last tier off the feature, and the Appearance stage
then lets go of a colour only a distinctive feature may hold. With no quality authored it
renders nothing.

The first `draft.feature_points_free` points of qualities cost no CG points. Every sum the
frontend makes of a pick list goes through `chargedCost(picks, free)`
(`offers/syncHelpers.ts`): the prices together, less the part of the qualities the
allowance covers (`featureCost`). `useShownPicks` uses it for a save in flight and returns
`featureSpent`; `useSyncDistinctions` uses it when a save answers and writes
`feature_points_spent` into the cached draft. A draft fixture needs both
`feature_points_spent` and `feature_points_free`, or those sums are NaN.

## Counts and names in copy (#5207)

A string built from a count uses `countNoun(count, noun)` (`utils.ts`), so one of a thing
reads "1 pick" and "1 kind". A name the server sends in lower case (a statistic) goes
through `capitalize` before it is printed beside a name that is not.

## A stage opens at its top (#5198)

`CharacterCreationPage` sets the window's scroll to 0 when `draft.current_stage` changes,
whether by Next, Back or the stage list. A refetch of the same stage does not scroll.

## Key Features

- **Free navigation**: All stages clickable, incomplete stages show warning badge
- **Real-time validation**: Stage completion tracked, submit blocked until all required stages complete
- **Folio primitives** (entries, instrument frames, fields, choice rows) now back Origin,
  Heritage, Path, Gift, Attributes & Skills, Appearance, Identity, Final Touches, and Review;
  Lineage alone still carries the pre-Folio card/badge markup, pending Plan C (#3630).
  `SkillsSection`, mounted inside AttributesStage's frame, still uses the shadcn Accordion for
  its per-skill specialization panels. The Distinctions stage is retired (#3675): every
  chapter now offers its own distinctions through `ChapterOffers` instead.
- Interface chrome is OOC and plain (stages, Next/Back, Select/Selected); in-character text is confined to
  realm/codex prose and the player's own words; the game never speaks for the player (#3540)
- **Staff-only features**: "Add to Roster" button visible only to staff
- **Player-GM direct-to-roster (#3268)**: a non-staff account that owns at least one active
  GM-role table sees a "Finalize for My Table" button beside Submit, gated by the same
  completeness condition. Opens `FinalizeForTableDialog` — picks the target table, names a
  story, and finalizes onto that table's Available roster (`POST .../finalize-gm/`) without
  going through staff review.

## API Endpoints Used

- `GET /api/character-creation/starting-areas/` - List accessible areas
- `GET /api/character-creation/species/` - List species (filtered)
- `GET /api/character-creation/families/?area_id=&kind=` - List families, optionally
  filtered by area and one or more `FamilyKind` ids (the claimed-path Upbringing's
  `claimable_kind_ids`, #3617)
- `GET /api/roster/families/{id}/slots/` - The claimed family's open seats and counted
  openings, each seat with its `head_relation`, plus the house head's `head_name` (#5130)
- `GET /api/character-creation/can-create/` - Check eligibility
- `GET /api/character-creation/drafts/` - List user's drafts (returns array with 0-1 items)
- `POST /api/character-creation/drafts/` - Create new draft
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Draft detail operations
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's tradition + path.
  `useCGGifts(draftId, pathId, traditionId)` keys the cached list on all three
  (`characterCreationKeys.cgGiftsFor`, which starts with `cgGifts(draftId)`), so a change of
  path or tradition asks again (#5198)
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- `GET /api/character-creation/combat-styles/?draft_id=X` - The combat styles the draft's Tradition teaches, with how each attacks and defends (#4921)
- `GET /api/magic/resonances/` - Every Resonance with its `affinity_name`, unpaginated (the Gift
  stage's Resonance step; `GET /api/magic/affinities/` lists the Affinities, #4665)
- `GET /api/character-creation/glimpse-tags/` - List the active glimpse tag catalog (guided Glimpse flow, #2427)
- `GET /api/character-creation/form-options/{species_id}/?draft=X` - Trait palettes (`{traits, inherited}`; traits carry `is_required`, `?draft=` appends cross-line option groups from the draft's parents, #2815)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff direct add
- `POST /api/character-creation/drafts/{id}/finalize-gm/` - Player-GM direct-to-roster for a
  table they own (`target_table`, `story_title`, optional `story_description`) (#3268)
- `GET /api/character-creation/drafts/{id}/beats/` - The life's beats as this draft meets
  them (#4124, #4395: each with its `allowance`); the `backgrounds` offers come through
  `GET /api/character-creation/drafts/{id}/offers/?chapter=backgrounds` (#4872: each offer
  carries its `group`, `asks_figure_name` and `effects` with magnitudes; the response's
  `terms` give each lever's definition for the term popovers)
- `GET /api/character-creation/beginnings/{id}/perspectives/` - A beginning's shop-window
  perspective entries, ungated by codex knowledge (ADR-0224, #3281)
- `GET /api/character-creation/traditions/{id}/perspectives/` - Same, for a tradition
  (ADR-0224, #3281)

## Route

`/characters/create` - Main character creation page
