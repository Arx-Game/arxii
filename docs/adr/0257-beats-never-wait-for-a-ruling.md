# Beats never wait for a ruling

`BeatOutcome.PENDING_GM_REVIEW` was the fallback every machine-graded OUTCOME_TIER
beat fell into when its outcome didn't fit the authored data cleanly: a roll above or
below every authored tier, a fled or abandoned fight, or a missing outcome-mapping row
all parked the beat and left its stakes waiting for a GM to look at it later. In
practice a beat that parked rarely got a timely look, and a parked beat with open
stakes strands the story around it - nothing else can complete until someone notices
and rules on it. #3559 deletes the state and its machine paths outright, replacing
each cause with a structural resolution that never waits: an outlier roll clamps to
the best authored tier of the same polarity instead of parking (`clamp_tier_to_pool`);
a withdrawal (a fled or abandoned encounter) resolves the stakes contract's WITHDRAWAL
branches immediately and leaves the beat open for a future attempt
(`resolve_stakes_for_withdrawal`), rather than blocking on either a ruling or a
retry; a missing `EncounterOutcomeMapping`/`BattleOutcomeMapping` row is required
content, reported on the admin sentinel (#3444), not an alternate resolution path;
and a concluded fight or battle grades only the one beat it was started for
(`beat_for_scene_conclusion`), never every beat sharing the scene.

**Rejected: an adjudication endpoint.** A GM-facing "resolve the pending beat" surface
would have kept the state and just made the wait explicit instead of removing it - the
Arx I failure mode this spec names directly: judgment calls made after the fact, once
play has already moved on, produce rulings nobody remembers the context for and stories
that sit stalled waiting on staff bandwidth that never scales with the player count.

**Rejected: keeping the find-all grader.** Before #1760/#3559, a concluded encounter or
battle graded every UNSATISFIED OUTCOME_TIER beat linked anywhere on its episode, not
just the one it was actually run for. A brawl breaking out during a heist would close
the heist beat too, on the same roll, for an entirely unrelated reason. Scoping grading
to one beat is a precondition for deleting the pending state cleanly: a beat that isn't
this fight's objective needs to stay open regardless of how this fight goes, not get
swept up in whatever tier the unrelated fight happened to land on.

> Status: accepted · Source: session 2026-09-02 (#3559)
