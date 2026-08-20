# ADR-0224: The CG shop window serves perspective content ungated

**Status:** Accepted (2026-08-20, Tehom in-session) - extends ADR-0222.

Mid-chargen players have no roster entry, so codex knowledge rows do not exist
yet and non-public entries are invisible through the codex API; perspective
entries are viewer-only by design (ADR-0222), so the CG wizard could never show
them. Ruling: the beginnings and traditions viewsets expose
`GET .../{id}/perspectives/`, serving `is_perspective=True` grant content to any
authenticated CG-eligible user with no codex knowledge gating - while choosing
who to be, you hear each culture's own voice. Codex proper is unchanged: the
viewed culture still discovers a stereotype in play. Corollary authoring rule: a
perspective entry is shop-window content by definition - never put secret or
spoiler material in one.

**Rejected:** flipping perspective entries `is_public` (would make every
culture's opinions world-readable forever, gutting viewer-only discovery).
