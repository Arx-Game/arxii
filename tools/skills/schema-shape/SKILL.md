---
name: schema-shape
compatibility: polytoken
description: Use when a design/spec/plan proposes a new relational-database model, table, foreign key, join/bridge table, denormalized column, or a primary-key choice — before committing the spec or writing the migration.
---

# Schema Shape

## Overview

Before a new table, relationship, or primary key ships, defend it against six
questions instead of a list of rules. #3787 shows why: the maintainer
(TehomCD) questioned three proposed shapes on the same PR, each defensible in
isolation, and each collapsed into something smaller once asked to name an
existing alternative. A rule like "prefer nesting to edge tables" is advice an
agent can argue past; a question backed by a concrete precedent is much harder
to wave off.

**Default posture: normalize by default.** Denormalization is a last resort,
reached only after app-level caching has been tried and measured to fail —
never reached for by default, never justified by a hypothetical query-count
saving that was never priced. Don't add a new table or relationship when the
existing schema can express the fact reasonably efficiently — this is a
cost/benefit judgment, not literal absolutism; the point is to force the
judgment to be argued, not to forbid every new table outright.

**The output of this pass is a defense of the shape (or a smaller shape it
collapses into), never a mechanical veto.** The maintainer can be wrong; the
point is to force the argument to happen before a human has to make it a
third time.

## When to use

A design/spec/plan/diff proposes any of:
- a new model or table
- a new foreign key or many-to-many/bridge table
- a denormalized column (a copy of data derivable from an existing relationship)
- a primary-key choice, especially anything that isn't a plain surrogate integer/UUID

## The six questions

Answer each one for the surface being proposed. Cite the alternative you
considered and why it doesn't work — "there wasn't an alternative" is not an
answer, it's a sign you didn't look.

### 1. What existing structure could carry this fact?

Name the existing model/field/relationship and say specifically why it
can't carry the new fact — including fields that exist but are unwritten. An
unused self-FK is a strong hint the shape was already designed and half-built.

**Worked example (#3787, round 1):** `InteractionReply`, a per-reply bridge
table (child reference + parent reference + denormalized timestamps), was
built, reviewed, and merged into the branch. *"Why do we have an
InteractionReply? This really seems like it's reinventing threads."* Correct:
`InteractionThread.parent`, a self-FK, had existed **unwritten since #3757** —
a field designed and half-built, and the bridge table was building the other
half of it somewhere else. A reply to a reply is a nested thread, the way a
mailing list nests, not a new data structure. Dropped, along with its per-row
handler and the priming that existed only to feed it; two per-page query
budgets went down. (`src/world/scenes/models.py:974-980`; the rejection is
recorded, along with the unwritten-since-#3757 observation, in ADR-0293's
Decision 4 "rejected alternative" paragraph, `docs/adr/0293-reachability-governs-addressing-not-audience-promotion.md:102-119`
— the rest of that ADR's Decision 4 does not reflect the final shipped shape;
see #3825.)

### 2. Is this derivable from data we already have?

If yes, price the derivation honestly — query count, portability, nesting
depth — instead of assuming storage automatically wins. A "write-once"
justification inherited from review praise, and never priced against the
read cost it avoids, is not a price.

**Worked example (#3787, round 2):** `anchor_interaction` + `anchor_timestamp`,
two columns plus a `unique_thread_per_anchor` constraint, held "the row every
member answers." *"Isn't it just always the first interaction in the
thread?"* Correct: `min(id)` over the thread's members is the anchor — `id`
comes from a single sequence shared across every partition of the
partitioned interaction table, so it's globally unique and monotonic, and no
tiebreak or denormalized copy is needed. The columns were defended on a
write-once property that was never priced against the read cost it was
supposedly saving; #3757 had already rewritten `Interaction.thread`
post-broadcast, shipped, and nothing broke. Dropped, and
`unique_thread_per_anchor` became unnecessary because a row has one thread FK.

### 3. Is a human-meaningful value doing this row's primary-key identity work?

Default suspicion: almost anything that looks like a stable name/slug
identity has an edge case where someone wants to rename the row — and
renaming then means changing the row's actual database identity and every FK
pointing at it.

**This is not the same question as whether the row needs a `NaturalKeyMixin` /
`NaturalKeyConfig` cross-reference**, as documented in ADR-0163
(`docs/adr/0163-case-insensitive-natural-keys-and-opt-in-lookup-tables.md`).
That mechanism is the established way to give fixtures and admins a
human-meaningful lookup while the row's actual identity — its primary key —
stays a surrogate integer: 180 models already do this, resolving a
`natural_key()` tuple to a pk through a process-level index, never storing
the tuple as the identity itself. Reaching for `NaturalKeyMixin` is the usual
right answer instead of promoting a human-meaningful value to PK.

The narrow legitimate cases for a non-surrogate PK: a genuine one-to-one
relationship onto another entity's own identity, or a foreign key to
something outside our control whose identifier can never change. Even the
one-to-one case isn't automatic — see the next question.

**Adjacent evidence this failure mode is real in this codebase (not a PK
case itself, but the same root cause — trusting a human-authored name as a
stable machine identity):** `tradition.name == "Unbound"` was hardcoded at
four production call sites; renaming the row in admin would have silently
turned the behavior off with no error (#3676).

### 4. Who else already depends on this row's own identity?

Before collapsing a one-to-one relationship's primary key onto its parent's,
check for other foreign keys, views, or serializers that already assume the
row has its own id. A genuinely one-to-one relationship is not, by itself,
permission to collapse.

**Worked example, both directions:** `RoomProfile` and `CharacterSheet`
correctly share `ObjectDB`'s pk (both `primary_key=True` O2Os) — nothing else
needs their own identity, so any caller holding an `ObjectDB` can filter a
retargeted FK with `field_id=obj.pk` instead of fetching the profile/sheet
first (see CLAUDE.md). `Covenant.organization` is an equally genuine
one-to-one that deliberately did **not** collapse, because
`CovenantLegendCredit` and views/serializers already depend on `Covenant`'s
own id — the field is a plain `OneToOneField`, explicitly commented "NOT
primary_key=True" with the reason stated inline
(`src/world/covenants/models.py:89-98`).

### 5. What is this compensating for that actually exists?

Name the concrete condition the extra shape is working around. If you can't
point at rows that need it today, it's compensating for nothing.

**Worked example (#3787):** an add-nullable-then-alter migration dance was
built to handle legacy rows during the interaction-thread migration — for a
table holding **zero rows**. There was nothing to compensate for; the
straightforward migration was correct all along. (This lived only in PR
review comments on #3787, not in committed code — cited from #3815's issue
body, "round 2," since the migration itself was never merged in this form.)

### 6. What does it cost when it drifts?

Every denormalized fact has two copies, and one of them can go stale. Price
that concretely — don't treat storage as free just because it's already on
the row. Cross-reference `django_notes.md`'s "Avoid Denormalization" and
"Avoid Denormalized Foreign Keys" rules (`django_notes.md:472-473`) rather
than re-deriving them here.

**Worked example (#3787, round 3):** `root`, one column denormalizing the top
of a nesting tree, existed so a reader could group a whole exchange without
walking `parent`. *"Why do we need a root? The root of the thread is
literally the first one, by id. It's impossible to have a reply happen before
what it's replying to."* Correct: a walk up `parent` derives it, and the
approved spec keeps nesting shallow in three places, so the deep-chain case
that would justify denormalizing was designed out. The column had **already
caused a bug on the branch**: `SET_NULL` cleared it on thread deletion, and a
nested thread then resolved as its own exchange — one pose counted in two
groups. (Cited from #3815's issue body, "round 3," for the same reason as
question 5 — the column and its bug never reached committed code.)

## Grounding

This skill applies standing decisions; it does not re-litigate them:

- ADR-0007 — no JSON fields; every setting is a typed, queryable column.
- ADR-0008 — every concrete model uses `SharedMemoryModel`; see the
  `sharedmemory-model` skill.
- ADR-0010 — FK direction is specific→general; never a direct FK to `ObjectDB`.
- ADR-0012 — PostgreSQL only in production; use its features directly.
- ADR-0163 — `NaturalKeyMixin`/`NaturalKeyConfig` is the sanctioned
  human-meaningful lookup that doesn't touch the primary key.
- `django_notes.md`'s "Avoid Denormalization" / "Avoid Denormalized Foreign
  Keys" rules.

## Closing framing

This skill's output is a defense of the shape (or a smaller shape), never a
mechanical veto. TehomCD can be wrong about a specific case; the point of the
six questions is to force the argument to happen on the page, in the spec,
before a human has to make it happen out loud a third time.
