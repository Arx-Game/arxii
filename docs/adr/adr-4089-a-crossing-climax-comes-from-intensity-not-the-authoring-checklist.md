# ADR-4089-A: A Crossing's climax comes from intensity, never from the authoring checklist

**Status:** accepted (2026-10-03, #4089). **Related:** #4073 (Arx 1 GM rulings epic), ADR-0251
(Required-content sentinel), ADR-4089-B (the Soulfray wheel rulings from the same issue).

The Required-content panel lists authored rows the code hard-depends on. While extending it for
Audere, Audere Majora and Soulfray, a row was proposed that would require high-tier threat content
(a boss, or a named kind of fight) per tier boundary before a character could cross. No dashboard
row, probe or flag requires a boss or a particular kind of fight for a Crossing: the gate reads the
encounter's intensity (`world.magic.audere_majora._check_intensity_gate`), and intensity is tuned
by combat scenarios, not by this checklist, so higher-tier NPC threat entries are not a checklist
row either. **Rejected:** a REQUIRED row per boundary level demanding authored high-tier threat
content - it would turn an ordinary skirmish that reaches the right intensity into a
non-qualifying fight, and make a content gap look like a broken gate.
