# Realms glossary

Canonical terms for `world.realms`. See `AGENT_GLOSSARY_MAP.md` for the map.

- **Realm** — one of the six starting realms of Catenys (Arx, Luxen, Umbros, Inferna,
  Aythirmok, Ariwn), the `Realm` row: name, formal name, theme (palette). _Avoid_:
  region, kingdom (a kingdom is what a realm may call itself; Ariwn is "the Kingdoms").
- **Testament** — a realm's pitch, the prose its page opens on, authored as movements
  (`RealmTestamentSection`) that each end on a **motto** line; every testament opens on
  the shared **threshold line** ("One stands before us in Durance. Speak thy name and
  testament."). The reviewer's prose, entered in admin, never loaded from the repo.
  _Avoid_: pitch, ad, intro (the same thing named from outside the world).
- **Realms hub** — `/realms`, six cards (name, formal name, first motto), each a link to a
  realm page. _Avoid_: realm tree, realm menu (the World menu holds one link).
- **Realm page** — `/realms/<slug>`: the testament plus four windows onto rows kept for
  other reasons (societies, houses and organizations, the boards, the roster).
- **Names spoken here** — the realm page's two boards, by renown and by legend, over the
  realm's Active-roster characters; names and band labels, never a number. Not a
  leaderboard: #676's per-realm addition, kept diegetic in shape (ADR-0285).
- **Shop window** (of an organization) — the fields a house would put on its gate: name,
  words, colours, sigil, description, kind, society (`OrganizationShopWindowSerializer`).
