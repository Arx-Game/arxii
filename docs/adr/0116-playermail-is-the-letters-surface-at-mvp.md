# PlayerMail is the letters surface at MVP; tenure-routed anonymity is the mechanism

`world.roster.PlayerMail` (tenure-to-tenure, threaded via `in_reply_to`) is the whole letters
system for #2160 — compose/inbox at `/profile/mail`, in-scene quick-compose from the character
card (`SendLetterDialog` pre-filling `ComposeMailForm`), unread badge, and a `MAIL_ARRIVED`
websocket push on send. Routing through `RosterTenure` (not `AccountDB`) is what already buys
player anonymity: the recipient is addressed and displayed as "the current player of Character X,"
never by account, and the arrival push payload carries only `mail_id`/`sender_display`/`subject`
for the same reason. We deliberately did not build a separate in-fiction messenger/delivery layer
(travel time for physical letters, courier interception, forgeable seals) — that is a real,
interesting IC-mechanics question, but it is a distinct system from "can a player privately message
another player's current character," which `PlayerMail` already solves. Left as an open design
question, not filed as a follow-up (no separable spec exists yet).

> Status: accepted · Source: #2160
