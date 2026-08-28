# ADR-0243: The Commonplace Book is the logged-in container idiom

<!--
Numbering note (#3412 slice 2 task 4): this worktree's docs/adr/ topped out at
0242 (movement-redirection-is-authored-not-modeled, #3416) at task-4 time.
`git ls-tree origin/main docs/adr/` shows the same tip (0242), and no open PR's
file list touches docs/adr/ (checked via `gh pr list --json files`), including
the stacked #3420 (four-state-terminology-rulings). 0243 is the next number
clear of both this worktree's local tip and main's; re-verify at enqueue in
case another PR claims it in the meantime.
-->

**Status:** Accepted (2026-08-28, #3412 slice 2)

**Decision.** The Hall (`/` for an authed account, #3412 slices 1-2) and every
future logged-in container surface built from it adopt one shared visual idiom,
"the Commonplace Book" (Direction B, ratified by Apostate 2026-08-28): squared
hairline plates (`Plate`/`PlateHead`, `frontend/src/components/folio/`,
`rounded-none border` — never the shadcn `Card`'s rounded corners or shadow);
three type voices with fixed jobs (Cinzel small-caps names things — character
names, plate headings; Garamond/serif body speaks for the world — tidings,
gemits, in-fiction prose; sans-serif carries data — counts, timestamps, form
controls); primary-colored square count chips (`CountChip`) for "N things
waiting," with destructive red reserved exclusively for actual danger/loss
states, never routine unread counts; and portrait-prominent state signaling —
the account's characters render as portrait cards first, with text (docked
state, tidings counts, persona name) as the accessible equivalent alongside the
image, never image-only.

**Why.** The Hall is a screen a player opens many times a day (the "ten visits
a day" bar) between individual sessions of active, in-world play — it has to
read at a glance, not be studied. A squared, plate-based layout with a small,
disciplined type-voice vocabulary keeps every repeated visit legible without
re-parsing a new layout each time. Portrait-forward signaling exploits
face-recognition being faster than text-parsing for "which of my characters is
this" — the single most frequent glance this page serves. Reserving destructive
red exclusively for danger keeps color meaningful: a Hall with a dozen
routine-orange-or-red badges trains players to stop reading color as signal.

**Rejected alternative 1 — folio-maximal ("the Ledger").** Full parchment
texture, illuminated capitals, marginal ornamentation on every plate — the
Gatefold's visitor-facing device pushed further inward. Rejected because it
fails the glanceability bar this specific page has to clear: heavy decoration
that reads beautifully on a one-time landing page becomes friction on a page
opened ten times a day, where every visit re-pays a legibility tax for
ornament the player stopped noticing after the first visit.

**Rejected alternative 2 — app-native shadcn ("the Operations Desk").** Ship
the Hall in the same rounded-card, default-shadcn idiom as `/game`'s
management surfaces (wardrobe, technique builder, admin-adjacent tooling).
Rejected on two grounds: it institutionalizes the Gatefold/app seam (ADR-0227)
rather than closing it — a player who has just left the pre-login gatefold's
in-fiction voice would land on a bare operations console, undercutting the
sense that the Hall is still part of the game rather than a settings panel;
and it de-fictionalizes IC surfaces the Hall front-doors (character portraits,
tidings, org offers) by presenting them in the same chrome as an admin form,
flattening the world/tooling distinction the rest of the frontend maintains
(`docs/roadmap/design-tenets.md`).

**Consequences.** Any new logged-in container surface reaches first for
`Plate`/`PlateHead`/`CountChip`/`PersonaTiles`
(`frontend/src/components/folio/`) before building bespoke chrome; a proposal
to add a new folio primitive should first check whether an existing plate
composition covers it (Anti-Reinvention). `CountChip` stays reserved for
routine "N things waiting" counts — a genuinely destructive/at-risk state gets
its own explicit red treatment, not a repurposed `CountChip`. "The Hall" is
still a placeholder name (Apostate's to finalize; see the roster
`AGENT_GLOSSARY.md`), but the Commonplace Book idiom it establishes is not
placeholder — it is the idiom the next logged-in container inherits by
default.

> Status: accepted · Source: issue #3412 (slice 2), the Three Halls comparison,
> Apostate ratification 2026-08-28, `docs/roadmap/ROADMAP.md`
