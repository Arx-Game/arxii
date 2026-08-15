# Narrative glossary

**Ambient Emit**:
A periodic room-linger flavor line (`AmbientEmit`) that fires while occupants remain in a room
rather than only on arrival — roaming atmosphere and a room-state risk telegraph are the same
row type, distinguished only by whether it carries a state gate.
_Avoid_: ambient line (that's `AmbientEmoteLine`, the entry-triggered sibling), flavor text (too generic)

**Risk Telegraph**:
An `AmbientEmit` row whose `gate_stat_key` is set, so it only fires when a room's
cascade-resolved `world.locations` stat (e.g. CRIME) clears a threshold — making a room's
current danger level legible in text before anything happens. Never spawns an encounter itself.
_Avoid_: danger flavor, warning line
