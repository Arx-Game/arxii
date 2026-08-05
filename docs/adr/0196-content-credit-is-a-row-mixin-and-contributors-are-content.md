# ADR-0196: Content credit is a row mixin; contributors are content

## Status

Accepted

## Context

`tools/prose_report.py` measured 70,278 prose words across 2,032 rows in the
corpus, with no way to tell an authored line from a placeholder outside the
four markdown domains. (An earlier figure of 26,431 words counted only
`fixtures/` and missed the four markdown domains, which hold a further 43,781
words across 156 entries.) #2980's issue proposed moving the prose-bearing
fixture models onto `MARKDOWN_EXPORT_DOMAINS` so credit could ride the
frontmatter path exclusively; that premise did not hold, because a real
column already round-trips through `content_export` -> `load_entries` in both
directions, so a new markdown domain would have bought nothing a column
doesn't already have.

Classifying which text fields count as "prose" also could not be a name
heuristic. A first pass keyed off field-name patterns and silently missed
nine models carrying real player-facing prose (e.g. `flavor_text`,
`windup_telegraph`), so the classification in `core_management/prose_fields.py`
is an exhaustive, test-guarded list of all 57 content text-field names, split
into `PROSE_FIELD_NAMES` and `NON_PROSE_TEXT_FIELDS`, so a new text field on a
content model must land in one of the two or the classification test fails.

## Decision

Credit is four nullable columns - `written_by`, `written_on`, `reviewed_by`,
`reviewed_on` - added by an abstract `CreditedContent` parent
(`world.contributors.models`) that 83 content models now inherit. `written_by`
and `reviewed_by` are FKs to a new content model, `ContentContributor`
(natural key `["name"]`, registered in `CONTENT_MODELS`), not free text. The
account link lives on `evennia_extensions.PlayerData.contributor`, a nullable
OneToOne pointing at `ContentContributor`, the reverse direction from the
credit FKs above.

## Rationale

A free-text handle carries no identity: two rows crediting the same spelled
name are not provably the same person, and the value cannot be deduplicated
or linked to an account. An FK straight to `AccountDB` was rejected because it puts a
username into every exported contributor row, and `_resolve_natural_key_fields`
would then skip that row on any database where the account does not exist,
silently losing the credit on the next load rather than failing loudly.
Putting the account link on `PlayerData` instead of on `ContentContributor`
follows ADR-0010 (FK direction is specific to general): the
installation-specific account row points at the reusable content primitive,
never the reverse, so `ContentContributor` and the exported corpus never
carry an account reference at all.

**Rejected:** generalizing `Artist` (`evennia_extensions.models`, named as
part of `Media`'s shared shape in ADR-0146) to serve as the credit identity
too. `Artist` requires a `PlayerData` O2O, so it cannot credit someone with no
game account, and it has no natural key to export by. Its other fields are a
commissions marketplace (contact terms, payment status), not attribution.

## Consequences

`Media.created_by` still points at `Artist`, not `ContentContributor`;
converging the two credit identities is intended future work, and doing so
will supersede part of ADR-0146. `WeatherEmit` rows carrying a null `key`
predate the emit re-key done alongside this change and are not addressable by
the content pipeline until backfilled.

A `written_by`/`reviewed_by` naming a `ContentContributor` that is not in the
corpus, or a malformed `written_on`/`reviewed_on`, no longer costs the row.
Every OTHER FK-by-name or scalar field in this pipeline still fails (and
skips) the whole row on a bad value - right when the field is part of what
the row *means* - but a credit is editorial metadata, not content: it has no
bearing on whether the row itself is valid, so a misspelled writer name must
not delete an entire entry's authored prose over a typo in a byline (Tehom's
ruling, 2026-08-05). `_upsert_fixture_object` resolves the four credit fields
separately, and up front, via `_resolve_or_drop_credit_fields`: a value that
resolves is applied exactly as before; a value that fails is dropped from
that one row's `fields` (same "absent means leave this column alone"
convention every other optional field already follows) and the rest of the
row loads normally. The failure is never silent - it is appended to
`result.skipped`, the same per-row diagnostic list the CLI and the admin's
"Load private content repo" button already surface for every other skip
reason, so an operator still sees the typo, just without losing the prose
over it.
