# One round framework, three modes, as the shared RoundContext seam

A single `SceneRound`/`RoundContext` provides tempo in three modes — OPEN (immediate), POSE_ORDER
(quorum), and STRICT (deferred-initiative) — and combat is just a STRICT specialization while a
danger round is STRICT with `start_reason=DANGER`; we rejected a combat-only round system bolted
beside a separate social path. One seam means social Rounds (the common case) and combat share tempo,
turn order, and per-round effects instead of diverging.

> Status: accepted · Source: #1351, #520, ROADMAP
