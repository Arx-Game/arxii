# Action-centric dispatch through the player-action seam

Both the web client (WebSocket/REST) and telnet converge on `dispatch_player_action()`, which routes
each intent by backend (REGISTRY → `action.run()`, CHALLENGE, COMBAT, SCENE_ADAPTIVE) so every player
capability is a real `actions.base.Action`; we rejected per-channel command logic and a single flat
`action.run()`. The common shorthand "everything goes through `action.run()`" is imprecise — the
shared seam is the dispatcher, and `action.run()` is one backend it routes to.

> Status: accepted · Source: #1336, src/actions/base.py, player_interface.py
