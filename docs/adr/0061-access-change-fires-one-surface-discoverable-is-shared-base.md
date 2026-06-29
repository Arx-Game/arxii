# Access-change fires one shared surface; discoverability is a shared abstract base

When a character gains or loses access to techniques or capabilities from any source
(alternate-self assume/revert, covenant engage/disengage, character creation), the
notification and first-ever Discovery ceremony are handled by a single surface
(`announce_access_change` + `announce_achievement` in `achievements/discovery.py`);
callers never branch on source — capability handling is identical regardless of origin.
Discoverability (the `discovery_achievement` FK that triggers a `Discovery` + achievement
grant) is factored into a single abstract base, `DiscoverableContent`, shared by
`Technique` and `CovenantRole`; we rejected a GenericFK bridge (per ADR-0015, which
forbids polymorphic/ContentType models) and per-model duplication of the same field
(per ADR-0016, which requires one shared base per concept).

> Status: accepted · Source: issue #1606
