"""Name culture seed (#2827 phase 2) — regional name pools for NPC instantiation.

Style ruling (Apostate, 2026-07-29): names sit KIND OF close to real names
with slight variances — "Sella" instead of "Stella"; "Selah"-tier real-but-
uncommon is the ceiling of exotic. Avoid hard-to-pronounce Scandinavian/
Celtic spellings even in the Norse/English cultures.

Regional vibes (all with fantasy mixes):
- **Umbros** — fantasy England/UK: general fantasy + medieval-English variants.
- **Luxen** — fantasy French; enough that the vibe reads instantly.
- **Ariwn** — sleek, dangerous eastern-European (the vampiric/dhampir houses).
  Lycan CLAN surnames (Clan Fleshfeast, etc.) are authored Family/house rows,
  deliberately NOT in the commoner pool.
- **Aythirmok** — lightly fantasy Norse, kept pronounceable.
- **Inferna** — sexy Spanish/Italian mix (style-heirs of the Lyceum).

Surname pools are COMMONER pools only: noble surnames always come from
authored `roster.Family` rows (a noble is a noble of somewhere — the house
lives in a real barony), passed to ``generate_person_name(family=...)``.

Cultures link to their `Area` rows by name when those exist; on shards where
the region areas aren't built yet the culture seeds unlinked (staff link via
admin, or re-run the seed after the grid lands). A "Common Tongue" global
default (area NULL) guarantees instantiation always has a pool.

Name lists are agent-drafted starters — Apostate curates; adding/removing
entries is plain admin data.
"""

from __future__ import annotations

from world.npc_services.models import NameCulture, NameCultureEntry, NamePart

# culture name -> (area name | None, given names, commoner surnames)
_CULTURES: dict[str, tuple[str | None, list[str], list[str]]] = {
    "Common Tongue": (
        None,
        [
            "Sella",
            "Alys",
            "Maren",
            "Tamsin",
            "Rowan",
            "Joss",
            "Wynne",
            "Edwyn",
            "Ansel",
            "Tobin",
            "Hollis",
            "Corwin",
            "Annora",
            "Betrys",
        ],
        [
            "Ashdown",
            "Fenwick",
            "Millbrook",
            "Greaves",
            "Waybrook",
            "Hartlow",
            "Tannard",
            "Marlowe",
        ],
    ),
    "Umbran": (
        "Umbros",
        [
            "Sella",
            "Alys",
            "Tamsin",
            "Ysolde",
            "Maren",
            "Cedany",
            "Lavena",
            "Elowen",
            "Merryn",
            "Annora",
            "Betrys",
            "Wynne",
            "Sabeline",
            "Rosalinde",
            "Gwenna",
            "Idony",
            "Josselyn",
            "Edwyn",
            "Aldric",
            "Osric",
            "Bramwell",
            "Elric",
            "Wystan",
            "Joss",
            "Rowan",
            "Gavric",
            "Hollis",
            "Corwin",
            "Dunstan",
            "Benedic",
            "Roburn",
            "Ansel",
            "Tobin",
            "Warrick",
        ],
        [
            "Thatchwell",
            "Ashdown",
            "Briarwood",
            "Copperwell",
            "Fenwick",
            "Millbrook",
            "Hartlow",
            "Greaves",
            "Waybrook",
            "Stonemere",
            "Tannard",
            "Wickfield",
            "Marlowe",
            "Duncombe",
            "Aldergate",
        ],
    ),
    "Luxenne": (
        "Luxen",
        [
            "Eliane",
            "Maelle",
            "Sylvaine",
            "Amelune",
            "Coralie",
            "Isabeau",
            "Lisette",
            "Margaux",
            "Odile",
            "Vivienne",
            "Solenne",
            "Celestine",
            "Anouk",
            "Lucien",
            "Thierry",
            "Armand",
            "Baptiste",
            "Corentin",
            "Etienne",
            "Gaspard",
            "Olivier",
            "Remy",
            "Sylvestre",
            "Aurelien",
            "Marcelin",
            "Tristan",
        ],
        [
            "Beaumarais",
            "Charbonneau",
            "Lefevre",
            "Moreau",
            "Duval",
            "Fontaine",
            "Marchand",
            "Rousselin",
            "Vachon",
            "Delacourt",
            "Barbeau",
            "Chastain",
            "Villenoir",
            "Perrault",
            "Aubertin",
        ],
    ),
    "Ariwnese": (
        "Ariwn",
        [
            "Mirela",
            "Sorina",
            "Katarin",
            "Vesna",
            "Ilinca",
            "Zorya",
            "Nadya",
            "Petrona",
            "Casmira",
            "Elenya",
            "Marzena",
            "Ruxanda",
            "Dragos",
            "Milos",
            "Andrik",
            "Casimir",
            "Radu",
            "Sorin",
            "Vasilan",
            "Emeric",
            "Konstantin",
            "Zoran",
            "Lucian",
        ],
        [
            "Vladeni",
            "Morarin",
            "Lupescu",
            "Corbeanu",
            "Negrescu",
            "Draganesti",
            "Varga",
            "Stoyan",
            "Balaur",
            "Cernov",
            "Vaduva",
        ],
    ),
    "Aythirn": (
        "Aythirmok",
        [
            "Astrid",
            "Signy",
            "Runa",
            "Ylva",
            "Freyda",
            "Ingra",
            "Solva",
            "Thyra",
            "Eira",
            "Brenna",
            "Sigrun",
            "Katla",
            "Liv",
            "Bjorn",
            "Leif",
            "Soren",
            "Einar",
            "Gunnar",
            "Halvar",
            "Ragnor",
            "Sten",
            "Torvald",
            "Ulfar",
            "Vidar",
            "Eyrik",
            "Hakon",
            "Orin",
            "Kolgrim",
        ],
        [
            "Grimvold",
            "Skaldsen",
            "Fjordane",
            "Ironmoor",
            "Runeval",
            "Stavgard",
            "Wolfsund",
            "Havardsen",
            "Kettilson",
            "Brimhold",
        ],
    ),
    "Infernal": (
        "Inferna",
        [
            "Serafina",
            "Bianca",
            "Lucrezia",
            "Valentia",
            "Ines",
            "Rosaria",
            "Catalina",
            "Allegra",
            "Marisol",
            "Vittoria",
            "Esperia",
            "Sancia",
            "Fiorella",
            "Alessio",
            "Dario",
            "Emilio",
            "Raffaele",
            "Santino",
            "Matteo",
            "Lorenzo",
            "Cesare",
            "Alvaro",
            "Vicente",
            "Giancarlo",
            "Nico",
            "Salvatore",
            "Benicio",
            "Teodoro",
        ],
        [
            "Ferran",
            "Castellan",
            "Riva",
            "Duarte",
            "Marchetto",
            "Solano",
            "Corvara",
            "Albano",
            "Fiorenza",
            "Delgardo",
            "Santoro",
            "Vidal",
            "Lucarel",
        ],
    ),
}


def ensure_name_cultures() -> int:
    """Seed the regional name pools. Idempotent; re-links areas on re-run.

    Given/surname split: entries whose value appears in the surname list
    seed as SURNAME; everything else as GIVEN. Returns entries ensured.
    """
    from world.areas.models import Area  # noqa: PLC0415

    ensured = 0
    for culture_name, (area_name, given_names, surnames) in _CULTURES.items():
        culture, _ = NameCulture.objects.get_or_create(name=culture_name)
        if area_name and culture.area_id is None:
            area = Area.objects.filter(name__iexact=area_name).first()
            if area is not None:
                culture.area = area
                culture.save(update_fields=["area"])
        for value in given_names:
            _, created = NameCultureEntry.objects.get_or_create(
                culture=culture, part=NamePart.GIVEN, value=value
            )
            ensured += int(created)
        for value in surnames:
            _, created = NameCultureEntry.objects.get_or_create(
                culture=culture, part=NamePart.SURNAME, value=value
            )
            ensured += int(created)
    return ensured
