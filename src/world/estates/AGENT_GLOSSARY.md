# Estates — Agent Glossary

**Will**:
A character's unilateral testament (`estates.Will`, OneToOne CharacterSheet): bequest
lines, tagged executors, and the prose testament read aloud at a will-reading. The
unilateral member of the agreements family (`currency.Contract` is the bilateral one;
the family is a UI hub, not a shared model). Frozen once a settlement window opens.
_Avoid_: testament (for the whole record — testament is the prose field only).

**Bequest**:
One line of a will (`estates.Bequest`): a kind (specific item, coin amount, all coin,
building, business, residuary), its target, and exactly one recipient (persona XOR
organization). Items and businesses require character recipients. _Avoid_: legacy.

**Executor**:
A persona tagged on a will (`estates.WillExecutor`); any one of them may perform the
will-reading while the settlement is pending. _Avoid_: trustee.

**Estate Settlement**:
The window opened at death (`estates.EstateSettlement`, from `_mark_dead`) during
which the estate may be executed by the first of three doors — funeral finish,
will-reading, or the deadline sweeper (ADR-0133). PARKED = escheat unresolvable,
zero mutations applied, staff queue. _Avoid_: probate.

**Estate Heir**:
The single fall-through chain every failed delivery lands on: valid residuary
recipient → intestate heir (family-org head, then public-record next of kin) →
escheat org. _Avoid_: default heir.

**Escheat**:
The no-heir terminus: registered assets to the region's controlling org
(`Domain.owner_org`), corpse items' ownership cleared to genuine free loot.

**Estate Claim**:
An inherited grievance (`estates.EstateClaim`): an item stolen from the deceased and
never recovered; the claim (never the item) passes to the named recipient or estate
heir. Claimant-visible only — the holder is never notified. _Avoid_: bounty.

**Hot (stolen provenance)**:
An item whose latest theft was never resolved — the victim never reappears as a
recipient in the `OwnershipEvent` ledger (`items.services.provenance`). Receipt of
hot items is gated by the `receiving-stolen-goods` consent category (default-deny);
refusals are category-generic so provenance never leaks. _Avoid_: flagged, marked.
