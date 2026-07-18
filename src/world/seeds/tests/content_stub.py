"""Shared stub content-repo root for tests exercising ``seed_dev_database()``.

``seed_dev_database()`` (#2474 Decision 5) now loads the arx2-lore content
repo before running any cluster seeder, and raises loudly (``ContentError``)
when ``CONTENT_REPO_PATH`` is unset or invalid — no silent skip, no
synthetic in-repo fallback. Every existing test in ``world.seeds.tests``
that calls ``seed_dev_database()`` needs a real (if minimal) content root on
disk for the duration of the call. This mirrors
``web.admin.tests.test_content_load_views``'s tmp-dir +
``CONTENT_REPO_PATH`` env-patch pattern, reused here rather than
reinvented — every ``seed_dev_database()`` caller in this package needs
exactly the same stub.

Starter Gift/Technique/PathGiftGrant/Tradition catalog stub (#2474 review
fix, Decision 5): the retired ``seed_starter_gift_catalog()`` used to
synthesize this catalog in-repo on every call, so every ``stub_content_root()``
consumer got it for free regardless of what the stub itself provided. Now
that the catalog is real lore-repo content — loaded via
``core_management.content_fixtures.load_world_content()``, exactly like every
other content-repo domain — a test stub that omits it leaves
content-dependent consumers (``world.npc_services.seeds``'s Academy trainer
roles, ``world.progression.seeds.seed_durance_officiants``,
``world.seeds.character_creation.seed_beginning_traditions``/
``seed_metallic_order_tradition``) with nothing to find, either raising
(the trainer roles, per Decision 5) or silently skipping (the others, by
their own pre-existing defensive design). Rather than have every consumer
suite hand-build a synthetic catalog via factories, this stub carries a raw
fixture JSON file (``fixtures/magic/starter_catalog.json``) reproducing the
retired seed's exact shape and names (5 PROSPECT Paths, 5 TechniqueStyles, 6
EffectTypes, 5 MAJOR Gifts with 5 authored Techniques each, the "Unbound"
Tradition, 5 PathGiftGrant + 5 TraditionGiftGrant rows) through the SAME
``load_world_content()`` path real lore content takes — every
``stub_content_root()`` consumer keeps working unchanged, and the shapes stay
identical to what a real content repo will eventually ship (natural-keyed,
loaded via ``build_fixture_json``'s raw-fixture-JSON scan, not a bespoke
frontmatter domain).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from unittest import mock

#: Name of the Trait row the stub fixture below creates — tests proving the
#: content load actually ran (not silently skipped) assert against this.
STUB_TRAIT_NAME = "Seed Test Stub Skill"

_STUB_SKILL_MD = f"""---
name: {STUB_TRAIT_NAME}
category: general
---
PLACEHOLDER stub content-repo skill; exists only so seed_dev_database()'s
tests have a minimal valid content root to load.
"""

#: Canonical name every consumer (production + tests) looks up by (mirrors
#: ``world.character_creation.constants.UNBOUND_TRADITION_NAME``, duplicated
#: here rather than imported so this module stays Django-import-light like
#: the rest of the file — it's a plain string, not a live reference).
UNBOUND_TRADITION_NAME = "Unbound"

#: (path_name, path_description, action_category) — the 5 canonical PROSPECT
#: paths, unchanged from the retired ``seed_starter_gift_catalog()`` (#2426).
_STUB_PATHS: list[tuple[str, str, str]] = [
    (
        "Path of Steel",
        "Warriors who temper themselves through hardship and direct action.",
        "PHYSICAL",
    ),
    (
        "Path of Whispers",
        "Those who move unseen, trading in secrets and subtle influence.",
        "SOCIAL",
    ),
    (
        "Path of Voice",
        "Performers whose magic resonates through song, story, and presence.",
        "SOCIAL",
    ),
    (
        "Path of the Chosen",
        "Devotees bound to a higher power whose prayers shape reality.",
        "MENTAL",
    ),
    (
        "Path of Tomes",
        "Scholars who unlock magic through careful study and written lore.",
        "MENTAL",
    ),
]

#: (style_name, style_description, linked_path_name)
_STUB_STYLES: list[tuple[str, str, str]] = [
    (
        "Manifestation",
        "Magic made tangible — raw elemental force given shape and weight.",
        "Path of Steel",
    ),
    (
        "Subtle",
        "Magic woven into the fabric of things — invisible until it strikes.",
        "Path of Whispers",
    ),
    (
        "Performance",
        "Magic amplified through art — voice, gesture, and presence as conduit.",
        "Path of Voice",
    ),
    (
        "Prayer",
        "Magic granted by devotion — the higher power answers through the faithful.",
        "Path of the Chosen",
    ),
    (
        "Incantation",
        "Magic encoded in language — formulae, glyphs, and spoken true names.",
        "Path of Tomes",
    ),
]

#: (effect_type_name, description, category)
_STUB_EFFECT_TYPES: list[tuple[str, str, str]] = [
    ("Weapon Enhancement", "Imbues a held weapon with magical force.", "buff"),
    ("Ranged Attack", "Projects destructive energy at a distant target.", "attack"),
    ("Buff", "Enhances the caster or an ally with a temporary magical boon.", "buff"),
    ("Debuff", "Weakens or hampers a target with a magical affliction.", "debuff"),
    ("Defense", "Interposes magical protection between the caster and harm.", "defense"),
    ("Utility", "Produces a practical magical effect with no direct combat role.", "utility"),
]

#: style_name -> (gift_name, gift_description) — one starter MAJOR Gift per style.
_STUB_GIFTS_BY_STYLE: dict[str, tuple[str, str]] = {
    "Manifestation": (
        "Emberwork",
        "Raw elemental force given shape and weight, wielded by main force.",
    ),
    "Subtle": (
        "Shadowcraft",
        "Magic that hides in plain sight, striking from an unseen angle.",
    ),
    "Performance": (
        "Resonant Chorus",
        "Magic amplified through voice, gesture, and presence.",
    ),
    "Prayer": (
        "Sacred Communion",
        "Magic granted through devotion, channeling a higher power's favor.",
    ),
    "Incantation": (
        "Glyphwork",
        "Magic encoded in inscribed formulae and spoken true names.",
    ),
}

#: (style_name, technique_name, description, effect_type_name) — 5 per style
#: (25 total), unchanged from the retired ``seed_starter_gift_catalog()``'s
#: 5x5 grid. ``world.npc_services.seeds``'s ``_SELF_STUDY_STARTER_TECHNIQUES``/
#: ``_GENERALIST_TRAINER_STARTER_TECHNIQUES`` reference the "attack" row
#: (Burning Strike/Shadow Blade/Shattering Chorus/Smiting Light/Force Sigil)
#: by (gift, name) — keep those five (gift, name) pairs in sync with this list.
_STUB_TECHNIQUES: list[tuple[str, str, str, str]] = [
    # --- ATTACK ---
    (
        "Manifestation",
        "Burning Strike",
        "A lance of raw fire conjured from personal will and hurled at the enemy.",
        "Ranged Attack",
    ),
    (
        "Subtle",
        "Shadow Blade",
        "A blade wreathed in shadow strikes from an unexpected angle.",
        "Weapon Enhancement",
    ),
    (
        "Performance",
        "Shattering Chorus",
        "A keening note tears through armor and resolve alike.",
        "Ranged Attack",
    ),
    (
        "Prayer",
        "Smiting Light",
        "Holy radiance descends on the unworthy, burning like judgment.",
        "Weapon Enhancement",
    ),
    (
        "Incantation",
        "Force Sigil",
        "A rune of impact is inscribed mid-air, detonating on contact.",
        "Ranged Attack",
    ),
    # --- DEFENSE ---
    (
        "Manifestation",
        "Iron Skin",
        "The caster's flesh hardens momentarily into something like cooled metal.",
        "Defense",
    ),
    (
        "Subtle",
        "Blur Step",
        "Subtle distortions make the caster hard to track — blows glance aside.",
        "Defense",
    ),
    (
        "Performance",
        "Resonant Ward",
        "A harmonious tone creates a shimmering barrier that absorbs incoming force.",
        "Defense",
    ),
    (
        "Prayer",
        "Sacred Ward",
        "The devout invoke their patron's shelter; harm slides off like rain.",
        "Defense",
    ),
    (
        "Incantation",
        "Arcane Barrier",
        "An inscribed ward springs up and deflects the next magical blow.",
        "Defense",
    ),
    # --- BUFF ---
    (
        "Manifestation",
        "Surge",
        "Raw vitality floods the target's limbs, sharpening reflexes for a moment.",
        "Buff",
    ),
    (
        "Subtle",
        "Unseen Edge",
        "Whispered magic gifts the target preternatural awareness of threats.",
        "Buff",
    ),
    (
        "Performance",
        "Inspiring Refrain",
        "A rousing melody lifts allies' spirits and sharpens their focus.",
        "Buff",
    ),
    (
        "Prayer",
        "Blessing of Strength",
        "A murmured prayer calls down divine favor onto a willing recipient.",
        "Buff",
    ),
    (
        "Incantation",
        "Empowering Glyph",
        "A brief formula inscribed on the target's skin grants temporary potency.",
        "Buff",
    ),
    # --- DEBUFF ---
    (
        "Manifestation",
        "Leaden Aura",
        "Palpable magical weight presses down on the target, slowing movement.",
        "Debuff",
    ),
    (
        "Subtle",
        "Doubt's Touch",
        "A whisper in the mind erodes the target's certainty at a critical moment.",
        "Debuff",
    ),
    (
        "Performance",
        "Discordant Note",
        "A jarring sound disrupts the target's concentration and coordination.",
        "Debuff",
    ),
    (
        "Prayer",
        "Mark of Penitence",
        "The caster's deity marks the target, making all blows against them more telling.",
        "Debuff",
    ),
    (
        "Incantation",
        "Unraveling Hex",
        "A compact curse formula frays the target's magical and physical defenses.",
        "Debuff",
    ),
    # --- UTILITY ---
    (
        "Manifestation",
        "Mending Touch",
        "Elemental force knits broken objects or calms a raging fire with a touch.",
        "Utility",
    ),
    (
        "Subtle",
        "Silent Passage",
        "The caster's presence dampens sound and scent — ideal for moving unseen.",
        "Utility",
    ),
    (
        "Performance",
        "Lullaby",
        "A soft melody coaxes fatigue into the listener, easing them toward sleep.",
        "Utility",
    ),
    (
        "Prayer",
        "Gentle Mending",
        "A prayer of restoration closes minor wounds and soothes pain.",
        "Utility",
    ),
    (
        "Incantation",
        "Light Script",
        "A luminous glyph provides clean magical light until dismissed.",
        "Utility",
    ),
]


def _build_starter_catalog_fixture_objects() -> list[dict]:
    """Build the raw-fixture-JSON object list for the starter catalog stub.

    Dependency order (Path/Style/EffectType/Gift before Technique before
    Tradition/PathGiftGrant/TraditionGiftGrant) so ``load_world_content()``'s
    natural-key resolution succeeds on the first pass — its deferred-retry
    mechanism would paper over a wrong order anyway, but there is no reason to
    rely on it here.
    """
    objects: list[dict] = []

    for name, description, action_category in _STUB_PATHS:
        objects.append(
            {
                "model": "classes.path",
                "fields": {
                    "name": name,
                    "description": description,
                    "stage": 1,  # PathStage.PROSPECT
                    "minimum_level": 1,
                    "action_category": action_category,
                },
            }
        )

    for name, description, _linked_path_name in _STUB_STYLES:
        objects.append(
            {
                "model": "magic.techniquestyle",
                "fields": {"name": name, "description": description},
            }
        )

    for name, description, category in _STUB_EFFECT_TYPES:
        objects.append(
            {
                "model": "magic.effecttype",
                "fields": {"name": name, "description": description, "category": category},
            }
        )

    for gift_name, gift_description in _STUB_GIFTS_BY_STYLE.values():
        objects.append(
            {
                "model": "magic.gift",
                "fields": {"name": gift_name, "description": gift_description},
            }
        )

    for style_name, technique_name, description, effect_type_name in _STUB_TECHNIQUES:
        gift_name, _gift_description = _STUB_GIFTS_BY_STYLE[style_name]
        objects.append(
            {
                "model": "magic.technique",
                "fields": {
                    "gift": [gift_name],
                    "name": technique_name,
                    "style": [style_name],
                    "effect_type": [effect_type_name],
                    "anima_cost": 5,
                    "description": description,
                },
            }
        )

    objects.append(
        {
            "model": "magic.tradition",
            "fields": {
                "name": UNBOUND_TRADITION_NAME,
                "description": "The tradition-less path — practitioners who answer to no school.",
            },
        }
    )

    style_to_path = {style_name: path_name for style_name, _desc, path_name in _STUB_STYLES}
    for style_name, (gift_name, _gift_description) in _STUB_GIFTS_BY_STYLE.items():
        path_name = style_to_path[style_name]
        gift_technique_names = [
            technique_name
            for row_style_name, technique_name, _desc, _et in _STUB_TECHNIQUES
            if row_style_name == style_name
        ]
        objects.append(
            {
                "model": "magic.pathgiftgrant",
                "fields": {
                    "path": [path_name],
                    "gift": [gift_name],
                    "starter_techniques": [[gift_name, name] for name in gift_technique_names],
                },
            }
        )
        objects.append(
            {
                "model": "magic.traditiongiftgrant",
                "fields": {
                    "tradition": [UNBOUND_TRADITION_NAME],
                    "gift": [gift_name],
                },
            }
        )

    return objects


@contextmanager
def stub_content_root() -> Iterator[Path]:
    """Build a tmp content root with valid fixtures; patch CONTENT_REPO_PATH.

    Usable as a context manager (``with stub_content_root():``) or, since a
    ``@contextmanager``-built generator function's return value doubles as a
    ``contextlib.ContextDecorator``, as a test-method decorator
    (``@stub_content_root()``) — each call/decoration gets its own fresh tmp
    dir, so it is safe to stack on multiple test methods in the same class.

    Writes two things: the original stub skill (``skills/stub.md``, a
    frontmatter-domain file — proves the content load actually ran) and the
    starter Gift/Technique/PathGiftGrant/Tradition catalog (a raw fixture-JSON
    file under ``fixtures/``, since that catalog isn't one of the frontmatter
    domains ``core_management.content_fixtures.DOMAIN_BUILDERS`` knows about —
    see the module docstring for why every consumer needs this.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill_path = root / "skills" / "stub.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_STUB_SKILL_MD, encoding="utf-8")

        catalog_path = root / "fixtures" / "magic" / "starter_catalog.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(
            json.dumps(_build_starter_catalog_fixture_objects(), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        with mock.patch.dict("os.environ", {"CONTENT_REPO_PATH": str(root)}):
            yield root
