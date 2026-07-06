# Battle live updates are a slim BATTLE_STATE ping plus REST refetch, not a full-state WS payload

The strategic battle-map page (#2009) needs live updates: a participant watching the map should
see the round advance, VP change, and unit/place state shift as the GM resolves rounds, without
reloading the page. We chose a slim WebSocket ping — `BATTLE_STATE` carries only
`{battle_id, round_number}` (`web.webclient.message_types.BattleStatePayload`) — over pushing the
full battle aggregate through the socket. On receipt, the frontend
(`hooks/handleBattleStatePayload.ts`) applies no data from the payload at all; it just invalidates
the React Query cache (`battleKeys.all`), which triggers a refetch of the same
`GET /api/battles/<pk>/` aggregate (`BattleDetailSerializer`) the page already reads on load. This
keeps `BattleDetailSerializer` the single source of truth for battle shape — there is no second,
independently-maintained WS payload shape that can drift out of sync with the REST one as the
aggregate grows (sides/places/units/participants/fortifications/vehicles). The ping is sent from
`world.battles.services.notify_battle_state_changed`, called from `begin_battle_round`,
`resolve_battle_round`, and `conclude_battle`, each deferring the send via
`transaction.on_commit` — so it always fires after the triggering transaction actually commits,
and a client that refetches on receipt is guaranteed to read committed state, never a
partially-applied round. We rejected pushing the full aggregate over the socket (duplicates
`BattleDetailSerializer`'s shape in a second, hand-maintained WS payload, with real drift risk as
the aggregate evolves) and rejected polling (adds latency between a round resolving and the map
updating, and wastes requests on inactive battles).

> Status: accepted · Source: #2009
