# Bulk resolution uses honest terminal states

Bulk close/resolve/archive operations must never block on absent players, never falsely mark
unresolved items "done," and never orphan them — they move loose ends to an honest terminal state
(e.g. story FORECLOSED) and track wrap-up as follow-up; we rejected a single optimistic "done" that
papers over reality. An honest terminal state keeps the records truthful when not everything could
actually be completed.

> Status: accepted · Source: #1185/#759, memory
