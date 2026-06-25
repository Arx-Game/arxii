# No polymorphic / GenericFK / ContentType models

Relationships are modeled concretely with real FKs; we categorically reject GenericForeignKey /
ContentType polymorphism. Generic FKs forfeit type safety, referential integrity, and clear queries —
a concrete model per relationship is always preferred even at the cost of more tables.

> Status: accepted · Source: memory
