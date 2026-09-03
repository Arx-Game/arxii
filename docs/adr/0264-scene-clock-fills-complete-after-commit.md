# ADR-0264: A scene clock fill completes the beat after commit, and the GM gesture spends ticks, never outcomes

**Status:** Accepted (#3567, 2026-09-03). Extends ADR-0030, ADR-0240, ADR-0256.

**Context.** #3567 adds an authored countdown (`Beat.clock_size`, `SceneClock`) filled by combat round starts (`begin_declaration_phase`, inside the round's own `@transaction.atomic`) and by a GM `advance_clock` gesture. Filling must resolve the beat EXPIRED through the real completion tail (`complete_beat_expired`, #3558): pool fires, stakes grade LOSS, contract closes, players are notified.

**Decision.** `tick_scene_clock` stamps the clock FILLED inside the caller's transaction and schedules the completion with `transaction.on_commit`; the callback locks the beat, re-checks it is still UNSATISFIED, and only then completes it, in its own transaction. The gesture takes only `by` (a tick count); the size and the consequence live on the beat, authored before play.

**Why.** A completion players were told about must never be rolled back by a later failure in the same round pipeline (the reaction-reset, DoT and escalation code that runs after the round increment). Lock-then-check makes a double tick or a concurrent SUCCESS completion a no-op instead of a second completion. Keeping outcome off the gesture is ADR-0030/ADR-0240: the GM paces, the author decides.

**Rejected.** Completing synchronously inside the round transaction (a later exception undoes a notified completion). A GM "time's up" action that completes EXPIRED directly (an un-authored consequence, and a second completion path beside the clock). Fiction-time deadlines on the game calendar and progress tracks as stakes (the issue's other two options; not chosen).
