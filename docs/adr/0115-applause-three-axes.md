# Applause is three axes, not one economy

Player-to-player positive feedback on a pose stays split across three independent
mechanisms, each with a distinct purpose: `WeeklyVote` is **popularity** — a scarce,
budgeted weekly resource that ranks poses (feeds the scene highlight reel's all-time
ordering) and settles into `MEMORABLE_POSE` XP for the top-ranked poses each week.
`award_kudos` is **graciousness** — an unlimited, GM/player-awarded "good sport"
currency with its own audit trail (`KudosTransaction`), claimable for XP later, and
now pushing a real-time `kudos_received` WS toast on every award (#2161). `emoji
InteractionReaction` is **expression** — cosmetic by default, but a nonzero-valence
emoji additionally fires an ambient relationship bump at the pose's author
(`ReactionEmoji.valence`, #1699) — a lightweight relationship-building signal
distinct from both. Endorsements (`world.relationships`) are a separate, fourth axis
entirely — the resonance/relationship-depth economy — named here only to draw the
boundary: it is not merged into any of the three above either.

We rejected merging these into one unified "applause economy": the three signals
answer different questions (was this popular vs. was this player gracious vs. how did
this specific beat land emotionally) and already had independent storage, UI
surfaces, and settlement timing before #2161 audited them. Collapsing them would have
required picking one settlement cadence and one XP conversion rate for mechanically
unrelated behaviors, and would have thrown away the weekly-budget scarcity that makes
votes meaningful as a ranking signal. #2161's job was reconciliation of what was
half-wired (the highlight reel wasn't ranking on votes at all; kudos had no
real-time push; `VoteButton`/`VotesPanel` weren't mounted), not consolidation of the
three into fewer mechanisms.

> Status: accepted · Source: #2161, Tehom's ruling on 2026-07-10
