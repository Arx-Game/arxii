# Combat

The Arx I combat system revolved around a turn queue with scripts handling abilities and damage. Arx II will take the opportunity to reinvent these mechanics. Our guiding principle is to create dramatic, cooperative moments rather than strict simulation. Combat is largely asymmetrical: player characters face enemies, large battles or boss monsters in various PvE scenarios.

Planned changes:

- Resolution and messaging run through the command system so modifiers can come from data tables.
- States expose permissions like `can_attack` or `can_flee` and internal utilities execute rolls and apply damage.
- Players are rewarded for coordinating actions; team combos confer bonuses that a lone fighter cannot achieve.

PvP conflict is possible only when all participants share a high level of trust and explicitly consent. Rivalries may exist, but open antagonism between characters is prohibited unless their players are friendly with one another.

We will reference Arx I only for inspiration. The new approach should feel familiar but ultimately provide a smoother and more satisfying experience.
