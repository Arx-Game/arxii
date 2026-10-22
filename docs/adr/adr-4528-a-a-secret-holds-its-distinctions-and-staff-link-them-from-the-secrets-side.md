# ADR-4528-A: A secret holds its distinctions, staff link them from the secret's side, and a secret may name a persona and a story

**Date:** 2026-10-21
**Status:** Accepted (ApostateCD, in session)
**Issue:** #4528 (relates #1334, #4397, ADR-0010)

## Decision

`CharacterDistinction.secret` is a plain foreign key, not a one-to-one: one secret holds any
number of the subject's distinctions, a distinction sits in at most one, and a linked
distinction is private (unchanged). The link is driven from the secret's side: on a secret,
staff see the subject's held distinctions and tick every one that belongs to it
(`set_secret_distinctions`); unticking makes a distinction public again and never deletes the
secret. `clear_distinction_secret` deletes a secret only when nothing else stands on it, no
other distinction and no truth under it as a hook. A secret also carries two staff-set links
the player never writes or reads: `about_persona`, who it is about when not the subject (the
demon behind a voice, a familiar, a person), and `story`, the story the truth belongs to,
beside the deed, legend and scene anchors. Both point from the secret outward (ADR-0010).

## Rejected

A story or persona link on the distinction kind or the held row: the kind is a catalog entry,
and the held row already reaches its secret; the secret is where the truth and the GM's notes
live. Keeping the one-to-one and minting one secret per distinction: the maintainer's shape is
"on a secret, a staff can look at all the distinctions and then select all that would be
applicable to that secret, and if linked, they become secret/private as well". Deleting a
secret on the last unlink from the picker: staff are on its page, and a hook with truths or
knowledge rows is not the distinction's to delete.
