# ADR-0192: Materials are potential, never performance

**Status:** Accepted (2026-08-01, #2878)

Arx 1 scaled item stats by material tier (rubicund → alaricite), and anchored
craft difficulty per tier — so masters trivially made divine cheap goods while
material choice was a vertical stat ladder. We reject both. A material's
`material_grade` feeds the **quality score** (`skill-capped roll + grade`), and
quality is the single aggregator that scales the physical stat line, facet
contributions, and fashion aggregates — so material reaches everything *through*
quality and never through a material→stat table. This inverts Arx 1's difficulty
feel: the grade is a head start toward one fixed quality landscape, so divine
silk is a master's good day while divine plain cloth is a near-impossible legend.
Rarity buys potential (grade, future affinity, durability texture, economy
value), and the crafter's finished quality multiplies everything the item ever
grows into. **Alternative rejected:** per-material stat multipliers (simple,
familiar, and exactly the flat power ladder that made Arx 1 material choice a
shopping decision instead of an expressive one); also rejected: capacity-style
"more facet slots per material" (conceptually wrong — a facet is one motif
reflected on a character, so material scales *how brightly* intent realizes,
never *how many* intents fit).
