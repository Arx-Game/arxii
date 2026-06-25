# Range-partition the Interaction table

`scenes_interaction` is `PARTITION BY RANGE` (monthly, composite PK `(id, timestamp)`, BRIN indexes),
a deliberate one-way, PG-only commitment to scene-log scale; we rejected an unpartitioned table. The
price is structural — child tables that reference Interaction need `db_constraint=False`, and
post-partition columns must be added via late `AddField` — and we accept it for the write/scan volume.

> Status: accepted · Source: partition SQL, #572
