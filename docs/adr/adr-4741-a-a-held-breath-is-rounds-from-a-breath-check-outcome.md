# ADR-4741-A: A held breath is rounds bought by a breath check's outcome, ended by breathing

A condition flagged `holds_breath` (a smoke form, being underwater) lasts as many rounds as the
bearer's breath check buys. On application she rolls `BreathHoldConfig.check_type`, and its
outcome tier's `BreathHoldDurationAward.rounds` replaces the rounds the condition or technique
supplied. The countdown is the ordinary ROUNDS one, so combat ticks and out-of-combat settling
need nothing new, and the same rule serves a swimmer. We chose discrete outcome tiers over a
duration computed from stats: the owner reads only check totals, never named stats, and tunes
effects per outcome tier. We chose no separate breath pool, because the rounds are the hold;
a pool would be a second clock that both had to agree with it. Ending the hold early has one
door, `take_breath`. The bearer reaches it at will, with no roll (`TakeBreathAction`, telnet
`breathe`, the web Status panel). Any condition flagged `breaks_held_breath` reaches it when it
lands, which is how a coughing fit works. Its own resist roll is the check to avoid the cough.
We chose a flag over one `ConditionConditionInteraction` row per pair, since every cough would
otherwise need a row for every held-breath condition. `breath_runs_out_condition` is applied
only when the hold expires on its own, never when she breathes, so running out underwater
drowns her and choosing to surface does not. What makes her cough is authored, not coded: a
reactive trigger on her own `TECHNIQUE_CAST` (or any other event) applies the Coughing
condition, so no code is tied to casting.

> Status: accepted · Source: owner delegated the design 2026-10-27 ("take your best guesses", a duration system shared with swimming) · issue #4741
