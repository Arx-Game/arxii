# ADR-0098: Houses are Organizations; recognition/succession derive from kinship; pacts are union-bound

**Status:** Accepted (#1884)

A house is not a new model — it is an `Organization` with a `family` FK into the
kinship graph (#2062, ADR-0097). Recognition (who is born INTO the house) is a
per-realm rule table (`HouseRecognitionRule`) applied to public-record parentage
edges, and succession is a derivation over the same graph (`SuccessionLaw`:
house default + per-title override, so Umbral Tanistry can sit on the Imperial
title alone). Marriage pacts bind to a `Union` and die instantly when a spouse
dies (the CK2 rule) — commitments are coded rows (DOWRY moves treasury coin at
signing, SUBSIDY materializes an `OrgObligation`, RESIDENCY marries the junior
spouse into the senior family) so alliances fire mechanically, not by GM memory.
Domains are decorations on DOMAIN-level Areas whose holdings materialize
`OrgIncomeStream` rows — the existing collection/graft/settlement pipeline is
reused untouched. **Rejected:** a standalone `House` model (would duplicate
membership, ranks, reputation, treasury, and channels that Organizations already
own); person-level pact binding (leaves pacts dangling after remarriage);
bespoke house income models (parallel-economy sprawl). The automation here is
the floor, never a gate — heads of house create opportunities on top
(anti-dependency tenet).
