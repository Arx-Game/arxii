# Examine-time display extras render at the LookAction seam, not a typeclass hook

Every examine-time behavior (reactive scars via EXAMINE_PRE/EXAMINED, ranking displays,
captivity status, board postings, catering history, crafted provenance, room
functionaries/notice-board hint/heat, and mission dispatch) used to live on
`ObjectParent.at_examined`/`return_appearance` in `typeclasses/mixins.py`, a path with zero
live callers since real play renders through `LookAction` -> `BaseState.return_appearance`
instead (#3084). We moved the whole family into `actions.definitions.examine_extras
.gather_examine_extras`, called once from `LookAction.execute()` and
`LookAtItemAction._render_item()`, and deleted the dead typeclass layer rather than keeping
it as a fallback. Rejected: routing through the typeclass hooks instead, which would bypass
or duplicate the flows-layer appearance pipeline (glance mode, concealment-aware character
lists, area-quality suffix, dreamside); and a `BaseState.get_display_footer` seam, which
would force the general `flows` layer to import `world.*` subsystems (against ADR-0010) and
would fire examine events on every state render instead of once per deliberate look.

> Status: accepted · Source: issue #3084
