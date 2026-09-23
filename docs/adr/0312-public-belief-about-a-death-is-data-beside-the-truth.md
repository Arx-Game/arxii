# ADR-0312: Public belief about a death is data beside the truth, never a substitute for it

**Status:** Accepted (2026-09-23, #3983).

`Kinsperson.believed_deceased` is its own boolean field, set only by `record_public_belief`,
entirely independent of `is_deceased` — the private, mechanical truth. The rejected alternative
was a **single `is_deceased` flag** doing both jobs: the public record would have to say exactly
what the truth says, with no room for a faked death, a survivor nobody has confirmed alive, or a
hidden truth. This is precisely the "hidden truth" surface the Almanach's family tree already
renders — a name the world believes dead, distinct from what actually happened — and it only
exists because the two facts are separate columns on the same row rather than one flag standing in
for both. Nothing derives one field from the other: a caller reading "what does the world believe
happened here" and a caller reading "what actually happened" each read their own column, and
`record_public_belief` is the one seam that writes the public half.
