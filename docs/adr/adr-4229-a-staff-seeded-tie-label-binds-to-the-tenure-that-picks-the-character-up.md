# ADR-4229: A staff-seeded tie label binds to the tenure that picks the character up

**Status:** Accepted (2026-10-10, ApostateCD, on #3988's approved spec)
**Issue:** #4229 (piece E of #3988)
**Related:** ADR-0308 (ties: two sides, labels with awareness), ADR-0024 (declaring a label
is never consent-gated), #3957 (a previous player's labels stay inert until re-declared)

## Context

A label counts toward mutuality, and so toward the mutual-hostile consent gate, only when it
was declared under a tenure that is still open (`known_label_q`). That rule keeps a roster
successor from inheriting the previous player's rivalries as live consent. Staff placing a
new roster character into an existing group need its ties in place before anyone applies:
the applicant reads them on the sheet and applies for that character, rivals included. A
label staff declare on a character nobody plays has no tenure to declare it under.

## Decision

Staff labels are live by staff ruling. On a played character's side, staff declare under that
player's current open tenure, so the label counts at once, mutual-hostile consent included;
staff take responsibility for having asked the player. On a character nobody plays, the label
is declared with no tenure and `RelationshipLabel.staff_seeded = True`. It counts toward
nothing while it waits. When an application is approved, `bind_staff_seeded_labels(tenure)`
stamps every open waiting label on that character's sides with the new tenure, so the ties the
applicant saw are live from pickup. A label an earlier player declared keeps its ended tenure
and stays inert until re-declared; #3957's rule is unchanged.

## Rejected alternatives

Declaring the label under a staff member's tenure (it would close or never be the character's,
and consent would read the wrong person); counting a tenure-less label as known (every waiting
label would gate consent against a character no one plays); asking the new player to re-declare
each one (the applicant applied for the character as drawn, ties included, and the group's other
players already count on them).
