# Unified resolution: one roll path, data-sourced difficulty, graded outcomes

Every IC outcome routes through `perform_check` (by CheckType), with difficulty read from authored
model/config fields and results resolved through weighted Consequence Pools into graded outcomes; we
rejected ad-hoc `random.*`, hardcoded difficulty constants, binary pass/fail, and GM fiat. One roll
path keeps difficulty authored and outcomes graded everywhere instead of reinvented per feature.

> Status: accepted · Source: design-tenets.md, #548
