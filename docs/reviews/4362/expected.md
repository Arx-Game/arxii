# #4362 real-testing pass: expectations computed by hand from the #4333 spec BEFORE the run
Inputs (model defaults and seed, read from code/seed, not from any run output):
favored deed 100%, associated 50%, 1 favor per 10 item value, favored facet x200%, weekly deed cap 8 base,
Chosen earn bonus +100 (rate 200%), others 100%. Closing award base: CS 8, S 5, PS 3, F 2, CF 0.
Ombrin's rite (devotional) pays 2 base favor at every tier. Pledge: target 20, span 2 game weeks.

Ysmay (Chosen, 200%), web UI:
- take pledge with a prayer: progress 0
- deed: 3 favored resonance -> base 3 -> +6   (progress 6)
- deed: 2 associated resonance -> base 1 -> +2 (progress 8)
- sacrifice silk scarf (value 20, Silk): 2 x 200% = 4 -> +8 (progress 16)
- perform Ombrin's rite: base 2 -> +4 (progress 20) -> card "Ready to close"
- close: rite's own award NOT paid; closing award = base[tier] x 2 (CS 16, S 10, PS 6; F/CF first try -> nothing, retry offered)
Orla (rate 100, rollmod -100 so the rite fails), web dispatch:
- take; close at 0 progress refused (not at target)
- sacrifice copper bowl (120, no facet): base 12 -> +12 (progress 12)
- deed 8 favored -> base 8 -> +8 (progress 20); deed 3 more favored -> cap reached -> +0 (progress 20)
- close #1 (Failure or Critical Failure): nothing paid, close_attempts 1, retry offered, still open
- close #2: resolves whatever the tier; pays base[tier] x 1 (F 2, CF 0); no further attempt
Tobiah (rate 100), telnet: take; sacrifice brass lamp (100) -> +10 (progress 10 = half of 20)
- lapse (span ended, lifecycle tick): pays Partial Success award 3 -> +3; favor 13; no answer; card Lapsed
Hobb (rate 100), telnet: take; sacrifice clay cup (90) -> +9 (progress 9 < 10)
- lapse: pays nothing; favor stays 9; card Lapsed
Room: onlookers see the sacrifice/rite lines; no favor numbers in room text.

## Revision after session 1 (before any later step ran)
Observed: a pledge taken WITH a prayer at the shrine also logs a holy-site prayer, which pays its usual
1 base devotion (once per being per game week) and counts toward the pledge. Walkthrough A's sum
(6+2+8+4=20) leaves it out. Kept as built and flagged for the maintainer. Revised expectations:
- Ysmay: prayer 1 x 2 = +2 -> deeds +6 +2 -> sacrifice +8 -> rite +4 = 22 of 20, Ready to close.
- Tobiah: prayer +1, sacrifice +10 = 11 (>= 10) -> lapse pays Partial 3 -> favor 11 + 3 = 14.
- Hobb (no prayer): 9 < 10 -> lapse pays nothing -> favor 9.
- Orla (no prayer): 12 now; +8 deed -> 20; +3 more favored deed -> 0 (cap) -> 20.
