# Consent defaults are a category tree, not per-category flags

Per-category consent modes are resolved by walking a category's parent chain: the nearest
node (starting at the leaf) that carries an explicit player rule wins, and if none does, the
**root's** `default_mode` governs. A player sets one control — e.g. "All Antagonism" — and
every category beneath it follows, overriding only the specific leaves they want to differ.
A category's own `default_mode` is consulted **only when it is a root** (has no parent); a
non-root's own value is inert while parented. Whitelist/blacklist entries are checked anywhere
on the chain (a whitelist on a parent admits the actor for its children), and an absent
`SocialConsentPreference` row is not auto-allow — it resolves to the root default too, since
the only thing unique to the preference row is the `allow_social_actions` master switch.

We rejected the flat per-category `default_mode` audit (#2170's original framing): it would
have required setting and maintaining the opt-in default on every antagonism category
independently, with no single knob and no inheritance, and it left the batched scene-picker
sweep allow-only (out of agreement with the authoritative `consent_blocks_targeting`). The
tree makes "antagonism is opt-in" a one-line seed decision on the root (`FRIENDS_WHITELIST`)
and lets both resolution paths share one walk-up rule. There are deliberately **no floors**:
a leaf fully inherits its parent, so setting the root wide open also opens its children —
`theft` is therefore left as its own independent `ALLOWLIST` root rather than under
All Antagonism, to preserve the #1909 steal gate.

> Status: accepted · Source: #2170, Apostate ratification 2026-07-11
