# ADR-4570-A: Covert is a fact about the organization, not its type

**Date:** 2026-10-22
**Status:** Accepted (ApostateCD, in session)
**Issue:** #4570 (relates #2820)

## Decision

Whether an organization is clandestine lives on the organization: `Organization.is_covert`,
a checkbox on its admin page. The flag #2820 put on `OrganizationType` is dropped after a
data migration copies it onto every organization of a covert type. Every reader (the realm
roster, the event and combat pickers, the creation enemy questionnaire, association, the
covert membership secret, crisis audiences) reads the organization's own flag. A type is a
rank ladder and an enemy reach, nothing more.

## Rejected

Keeping the flag on the type: the designer, laying out a house on production, added a
"tradition" type and could not make its lodge secret, because the same type also holds an
open academy. Keeping both with "covert if either is set": two sources of truth for one
fact, and a checkbox that reads unchecked on an organization that is hidden anyway.
