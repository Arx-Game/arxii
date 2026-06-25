# CovenantRole and CovenantRank are orthogonal axes

Combat-power `CovenantRole` (Sword/Shield/Crown, carrying `speed_rank`) is a separate axis from
administrative `CovenantRank` (whose `can_invite`/`can_kick`/`can_manage_ranks` flags gate authority);
the two are never merged and there is no `is_leadership` flag on Role. We rejected collapsing power and
authority into one ladder so a powerful Sword can be administratively junior and a quiet Shield can run
the covenant.

> Status: accepted · Source: #1027, covenants.md · Confidence: derived-from-roadmap, verify against code
