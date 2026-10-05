# Tempo is action-driven, never wall-clock (AFK-safe)

Dangerous progression advances only when a player acts, driven off the RoundContext seam, never off
`game_clock`, so nothing harmful happens to a character while their player is AFK; we rejected
real-time tick progression. Any long-term scheduler tier is capped non-lethal precisely because it
can advance unattended.

One scoped exception: ADR-4120 settles round-counted effects into real time after combat, harm
clamped non-lethal.

> Status: accepted · Source: #520, design-tenets.md
