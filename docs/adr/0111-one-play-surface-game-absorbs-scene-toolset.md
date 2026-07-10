# One play surface — `/game` absorbs the scene toolset; `/scenes/:id` is the record page

The #2155 webclient audit found the scene toolset (threading, action attachment, places,
consent, composer modes) fully built but mounted only on `/scenes/:id`, while the live `/game`
view — where sessions, sockets, puppets, and movement actually live — rendered a flat monospace
log with no threading; #2156 closes this by making `GamePage` the composition root: it calls
`useSceneInteractions` + `useThreading` once for the active session's scene and feeds the result
to the left sidebar, center feed, and toolset, while `/scenes/:id` keeps `SceneInteractionPanel`
unchanged as the historical record/detail page. We rejected the reverse — making `/scenes/:id`
primary and redirecting play there — because sessions, WebSocket connections, puppet/character
switching, and movement are already anchored to `/game`; re-homing them to the scene page would
require duplicating or relocating that entire live-connection substrate for no gain, whereas the
toolset itself is comparatively cheap to lift into the existing play surface. This slate also
ratifies the chat-bubble presentation bar: the primary feed renders each interaction as an
avatar-thumbnail chat bubble (author, timestamp, prose, reactions) — monospace/terminal styling
on the primary feed is a defect, not an acceptable variant; system/channel/error output stays a
separate muted, compact, chat-app-style notice lane, never blended into the bubble feed. See
issue #2156.

> Status: accepted · Source: issue #2156, epic #2155
