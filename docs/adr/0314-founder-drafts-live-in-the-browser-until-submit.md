# ADR-0314: A founder's house claim lives in the browser until submit, never as a server-side draft row

**Status:** Accepted (2026-09-23, #3983 Plan B).

The founder's whole claim journey — pick a seat, name the house, write its kin tree, describe its
lands, pitch an estate — is authored client-side, kept in `localStorage` as the founder fills it in
(`frontend/src/almanach/founder/founderDraft.ts`, mirroring `world-builder/document/useDraft.ts`'s
existing localStorage discipline: every read/write try/catch wrapped, so private browsing, a quota,
or disabled storage degrade to "nothing remembered," never a crash), and reaches the server only
once, at `POST .../house-claim/`, which runs `submit_house_claim`'s automated gates and writes the
`HouseClaim` row (plus its nested `HouseClaimKin`/`HouseClaimLand` rows) in one transaction; nothing
is persisted server-side before that call, and a founder who abandons the Lineage stage mid-draft
leaves no trace in the database beyond the `CharacterDraft` itself. The rejected
alternative was a `DRAFT` `HouseClaimStatus` with server-side rows saved incrementally as the
founder moves through each chapter — reasoned about because it would let a founder resume a claim
from another device. It was rejected on two grounds: a `DRAFT` claim would reserve or visibly leak
an unsubmitted seat (another founder browsing the ladder could see a title "claimed" by an
application nobody has committed to, or `_validate_claim`'s title-uniqueness gate would have to
learn to ignore draft rows, weakening the very check it exists to run), and it would add a status
value every downstream reader — the staff review queue, the admin inlines, `claimable_titles`,
`ladder_for_realm` — would need to filter out, permanently, for a case (resuming a claim on a
second device) nobody asked for. `CharacterDraft` itself already persists server-side across the
whole CG flow, so a founder never actually loses their place — only the house-claim SUB-draft
stays client-side until the one atomic submit.
