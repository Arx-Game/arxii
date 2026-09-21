# Architecture Decision Records

This log records the *why* behind the hard, surprising, traded-off decisions that shape Arx II —
and the alternatives we rejected. An ADR captures a moment of reasoning so a future agent or human
doesn't relitigate a settled question or "fix" something that was deliberate.

`docs/roadmap/design-tenets.md` and the invariants in `CLAUDE.md` are the **forward-looking directives** —
they tell you what to do. The ADRs are the **record of why** that directive exists and what was
weighed against it. The two must stay in tandem: when a decision changes, update both the directive
and add (or supersede) the ADR in the same PR.

**Naming a new ADR:** use the issue that motivated the decision as its stable identifier. New
files begin `adr-<issue>-<slug>.md` and identify themselves as `ADR-<issue>`; if one issue
produces more than one decision, use `adr-<issue>-a-<slug>.md`, `adr-<issue>-b-<slug>.md`,
and so on, with identifiers `ADR-<issue>-A`, `ADR-<issue>-B`, and so on. Existing sequential filenames and
identifiers remain valid and are never renumbered.

## When to offer an ADR

Offer an ADR only when a decision clears all three bars:

1. **Hard to reverse** — undoing it later means a migration, a data rewrite, or churning many call
   sites, not flipping a flag.
2. **Surprising** — a competent newcomer would reasonably expect the opposite, so the choice needs a
   recorded rationale to survive.
3. **A real trade-off** — we gave up something concrete (portability, flexibility, idiomatic
   convention) to get something concrete; both sides are worth naming.

If a decision is none of these, it's just code — don't write an ADR for it.

## Format

Each ADR is one tight file: a decision-shaped H1 title, one short paragraph (1–3 sentences) giving
the context, what we decided, and why — including the rejected alternative — and a one-line footer.

```md
# {Short decision-shaped title}

{1–3 sentences: the context, what we decided, and why — including the rejected alternative.}

> Status: accepted · Source: {roadmap §X / issue #N / CLAUDE.md / memory}
```

No Status/Options/Consequences sections — keep it to the paragraph unless extra structure genuinely
earns its place. Use repo vocabulary (Persona, Scene, Round, seam, Action); don't redefine terms.
ADRs derived from the roadmap that name specific models/fields carry a "verify against code" note —
treat those names as hints to confirm, not gospel.

## Discovery

The ADR directory is the index. GitHub lists every record in `docs/adr/`, and the descriptive
filenames make browsing useful without a second catalog that can go stale or conflict. Search the
records when you need a decision by subject, issue, or identifier:

```sh
find docs/adr -maxdepth 1 -type f -name '*.md' -print | sort
rg -n -i 'search term|issue #123|ADR-123' docs/adr --glob '*.md'
uv run python tools/check_adr_links.py
```

Run the link check before opening a PR, then read the matching ADR files and follow their related-ADR links. Do not add new per-ADR entries to
this README; keeping this guide stable is what lets independent ADR changes merge cleanly.
