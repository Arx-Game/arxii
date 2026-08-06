# ADR-0202: Achievement earning is gated at the grant_achievement chokepoint, not per-caller

Achievement earning is gated on "current, non-staff RosterTenure" inside `grant_achievement`
itself, not in callers. Context: #2899 gated only `announce_access_change`; four other callers
(stat thresholds, worship favor, crossing/combo/signature ceremony beats, aura thresholds) stayed
ungated, letting a GM-piloted or mid-CG sheet silently consume a first-ever Discovery slot, and
the ceremony beat could fire the gamewide announcement, irreversibly spoiling an NPC: an NPC or
non-player-piloted character earning a discovery robs players of getting it, robs the surprise,
and spoils the NPC's own capabilities, and a spoiler cannot be taken back (#3024 ruling by
TehomCD, 2026-08-06). Decision: enforce at the single production write path for
CharacterAchievement/Discovery so current and future callers inherit the invariant; stat tracking
continues for ineligible sheets (a GM-authored roster character is built to player norms, so
grant-on-first-eligible-increment once a player takes tenure is acceptable, while a true NPC may
carry stats or levels unavailable to players for years and never gains tenure, so the gate holds
permanently for it). Rejected: per-caller gating (has to be re-remembered per new caller; the four
ungated callers are the proof) and freezing/resetting stats at tenure start (loses world-state
for no player-visible gain).

> Status: accepted · Source: #3024, TehomCD's ruling 2026-08-06 · Related: ADR-0061 (access-change
> fires one shared surface), #2899 (the narrower pre-#3024 ceremony-only gate)
