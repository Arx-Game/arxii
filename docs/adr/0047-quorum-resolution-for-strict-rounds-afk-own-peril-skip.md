# STRICT rounds resolve on a quorum; an AFK participant's own peril is skipped on the END tick

STRICT (and therefore danger) round completion switched from unanimity to a quorum
(`ceil(advance_quorum_pct / 100 × present_active_count)`, reusing the field POSE_ORDER already
uses; at 100 it reduces to the prior unanimity), so one conscious-but-AK participant can no longer
deadlock the round — and a GM lowering `advance_quorum_pct` via `set_scene_round_mode` re-checks
completion immediately. To keep ADR-0004's true intent (an AFK *character* is not harmed while
away), `resolve_scene_round` excludes an undeclared present `can_act` participant from the END-tick
target set, so their *own* acute conditions do not advance from a round they didn't engage in; the
prior unanimity rule had conflated "don't harm the AFK character" with "the round can't advance past
them." We rejected an explicit away/idle participant status and an N-round auto-pass — both add
machinery for a problem the quorum already solves. *Whose* declaration advances *whose* peril
(involved-party-only) is a separate question, owned by #1479.

> Status: accepted · Source: #1480 · Extends: ADR-0004
