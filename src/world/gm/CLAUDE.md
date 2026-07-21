# GM App

GM identity/trust (`GMProfile`, `GMApplication`, level caps), tables
(`GMTable`, `GMTableMembership`), story areas/rooms, the scenario catalog, and —
as of #2607 — the **table sheet-update request framework**. System reference:
`docs/systems/INDEX.md` (GM sections).

## Table Sheet-Update Requests (#2607)

A general end-of-session request surface: a table member asks their GM to change
something on their sheet, the GM signs off yes/no, and the member completes it.
**Distinction add/remove is the first (and currently only) kind.**

### The model + state machine

`TableUpdateRequest` (`models.py`): `membership` FK → `GMTableMembership`, a
`kind` (`TableRequestKind`), `player_reasoning`, `status` (`TableRequestStatus`),
`gm_notes`, and created/resolved/completed timestamps. Kind-specific payload
lives on a 1:1 **details** model (no JSON, ADR-0007) owned by the consumer app
(`distinctions.DistinctionChangeDetails` — the FK points *at* `TableUpdateRequest`;
`gm` never imports `distinctions`, ADR-0010).

```
PENDING --signoff(approve)--> APPROVED --complete--> COMPLETED
   |--signoff(reject)--> REJECTED
   |--withdraw--> WITHDRAWN
```

Transitions live in `table_request_services.py` (generic: `signoff_request`,
`withdraw_request`, `complete_request`, `TableRequestStateError`). **Submit is
kind-specific** and lives with the kind (`submit_distinction_request` in
`world.distinctions.table_request_handlers`). Approval fires a `NarrativeMessage`
prompting the member to complete; completion has **no deadline** and, if the
kind handler raises (e.g. the member can't afford the XP), the status stays
`APPROVED` for retry.

### Kind → handler registry (the extension seam)

`request_handlers.py` mirrors `world.npc_services.effects`: `REQUEST_HANDLERS`,
`register_request_handler(kind, handler)`, `run_request_completion(request)`.
A handler runs at **completion**, not approval.

**To add a new sheet-update kind:**
1. Add a `TableRequestKind` value in `constants.py`.
2. Add a 1:1 `*Details` model in the *consumer* app (FK → `gm.TableUpdateRequest`).
3. Write a `submit_<kind>_request(...)` in the consumer app (validates eligibility,
   computes any cost, creates the request + details in `PENDING`).
4. Write a completion handler `(request) -> None` and register it from the consumer
   app's `AppConfig.ready()` via `register_request_handler` — so `gm` never imports
   the consumer app.

The generic transitions (`signoff`/`withdraw`/`complete`) and the four REGISTRY
actions (`table_request_submit/withdraw/complete/signoff`, `actions/definitions/
table_requests.py`) work unchanged for any kind.

### Surfaces

- Telnet: `tablerequest` (alias `treq`) — submit/withdraw/complete/signoff + a hub.
- Web: the four actions are REGISTRY-dispatchable via the generic seam (ADR-0001);
  a web read-list viewset is a separable follow-up.
