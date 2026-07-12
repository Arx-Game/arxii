"""Content pipeline (#944): parsing, validation, fixture shape, idempotent load."""

from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase

from core_management.content_fixtures import (
    TRAIT_CATEGORIES,
    TRAIT_TYPES,
    ContentError,
    _resolve_natural_key_fields,
    build_all,
    load_entries,
    parse_content_file,
    write_fixtures,
)
from world.buildings.models import BuildingKind, DecorationKind
from world.buildings.seeds import ensure_decoration_kinds
from world.items.models import ItemTemplate
from world.npc_services.models import NPCRole
from world.societies.factories import OrganizationFactory
from world.traits.models import Trait, TraitCategory, TraitType


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


GOOD_SKILL = """---
name: Performance
category: social
---
PLACEHOLDER Captivating an audience through music, oration, or storytelling.
"""

GOOD_NPC_ROLE = """---
name: Builders Guild Clerk
faction_affiliation: Builders Guild
default_rapport_starting_value: 5
default_description_template: A harried clerk, stamp in hand.
---
Issues building permits on behalf of the Builders Guild.
"""

GOOD_ITEM = """---
name: Iron Longsword
value: 40
weight: 3.5
---
A well-balanced blade, plain but serviceable.
"""

GOOD_BUILDING_KIND = """---
name: Watchtower
---
PLACEHOLDER — a fortified lookout post.
"""

GOOD_DECORATION_KIND = """---
name: Great Hearth
---
A roaring stone hearth that drives out the worst of the cold.
"""


class ParseAndValidateTests(TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_enums_mirror_real_trait_choices(self) -> None:
        # TRAIT_TYPES is the producible subset; categories mirror exactly.
        assert {t.value for t in TraitType} >= TRAIT_TYPES
        assert {c.value for c in TraitCategory} == TRAIT_CATEGORIES

    def test_parse_good_file(self) -> None:
        path = _write(self.root, "skills/performance.md", GOOD_SKILL)
        entry = parse_content_file(path, "skills")
        assert entry.meta["name"] == "Performance"
        assert entry.has_placeholder is True

    def test_missing_frontmatter_fails(self) -> None:
        path = _write(self.root, "skills/bad.md", "just prose, no frontmatter")
        with self.assertRaises(ContentError):
            parse_content_file(path, "skills")

    def test_build_all_validates_and_counts_placeholders(self) -> None:
        _write(self.root, "skills/performance.md", GOOD_SKILL)
        _write(
            self.root,
            "stats/presence.md",
            "---\nname: presence\ncategory: social\n---\nForce of personality.\n",
        )
        _write(self.root, "worldbook/secret.md", "reference canon — ignored by the builder")
        result = build_all(self.root)
        assert len(result.entries) == 2
        assert result.placeholder_counts == {"skills": 1}
        outputs = set(result.fixtures)
        assert "world/traits/fixtures/content_skills.json" in outputs
        assert "world/traits/fixtures/content_stats.json" in outputs

    def test_bad_category_collects_error(self) -> None:
        _write(
            self.root,
            "skills/oops.md",
            "---\nname: Oops\ncategory: nonsense\n---\nbody\n",
        )
        with self.assertRaises(ContentError):
            build_all(self.root)


class NewDomainParseAndValidateTests(TestCase):
    """#2266: npc_roles/items/building_kinds/decoration_kinds shape validation."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        OrganizationFactory(name="Builders Guild")

    def test_good_files_parse_for_every_new_domain(self) -> None:
        _write(self.root, "npc_roles/clerk.md", GOOD_NPC_ROLE)
        _write(self.root, "items/longsword.md", GOOD_ITEM)
        _write(self.root, "building_kinds/watchtower.md", GOOD_BUILDING_KIND)
        _write(self.root, "decoration_kinds/hearth.md", GOOD_DECORATION_KIND)
        result = build_all(self.root)
        outputs = set(result.fixtures)
        assert "world/npc_services/fixtures/content_npc_roles.json" in outputs
        assert "world/items/fixtures/content_items.json" in outputs
        assert "world/buildings/fixtures/content_building_kinds.json" in outputs
        assert "world/buildings/fixtures/content_decoration_kinds.json" in outputs

        npc_fields = result.fixtures["world/npc_services/fixtures/content_npc_roles.json"][0][
            "fields"
        ]
        assert npc_fields["faction_affiliation"] == ["Builders Guild"]
        assert npc_fields["default_rapport_starting_value"] == 5
        assert npc_fields["default_description_template"] == "A harried clerk, stamp in hand."

        item_fields = result.fixtures["world/items/fixtures/content_items.json"][0]["fields"]
        assert item_fields["value"] == 40
        assert item_fields["weight"] == "3.5"

    def test_missing_name_collects_error_for_every_new_domain(self) -> None:
        _write(self.root, "npc_roles/bad.md", "---\ndescription: nope\n---\nbody\n")
        _write(self.root, "items/bad.md", "---\nvalue: 1\n---\nbody\n")
        _write(self.root, "building_kinds/bad.md", "---\n{}\n---\nbody\n")
        _write(self.root, "decoration_kinds/bad.md", "---\n{}\n---\nbody\n")
        with self.assertRaises(ContentError) as ctx:
            build_all(self.root)
        message = str(ctx.exception)
        assert message.count("'name' (string) is required") == 4

    def test_npc_role_bad_faction_affiliation_collects_error(self) -> None:
        _write(
            self.root,
            "npc_roles/ghost.md",
            "---\nname: Ghost Clerk\nfaction_affiliation: Nonexistent Guild\n---\nbody\n",
        )
        with self.assertRaises(ContentError) as ctx:
            build_all(self.root)
        assert "Nonexistent Guild" in str(ctx.exception)


class ContentLoadTests(TestCase):
    """End-to-end: build → load_entries twice → idempotent upsert.

    Uses load_entries, NOT loaddata: SharedMemoryModel's identity map makes
    natural-key loaddata silently drop updates (verified cross-process —
    see load_entries' docstring). Fresh-DB inserts via the emitted fixture
    JSON remain valid; the authoring loop must upsert.
    """

    def setUp(self) -> None:
        self.content = tempfile.TemporaryDirectory()
        self.addCleanup(self.content.cleanup)
        self.root = Path(self.content.name)
        _write(self.root, "skills/performance.md", GOOD_SKILL)

    def test_load_creates_then_updates_by_natural_key(self) -> None:
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        trait = Trait.objects.get(name="Performance")
        assert trait.trait_type == TraitType.SKILL
        assert "PLACEHOLDER" in trait.description

        # Author rewrites the prose; reload must UPDATE the same row.
        _write(
            self.root,
            "skills/performance.md",
            "---\nname: Performance\ncategory: social\n---\nThe rewritten voice.\n",
        )
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)
        assert Trait.objects.filter(name="Performance").count() == 1
        trait.refresh_from_db()
        assert trait.description == "The rewritten voice."

    def test_fresh_db_fixture_json_still_loads(self) -> None:
        """The emitted fixture files stay valid for fresh-DB seeding."""
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        written = write_fixtures(build_all(self.root), Path(out.name))
        call_command("loaddata", str(written[0]), verbosity=0)
        assert Trait.objects.filter(name="Performance").exists()

    def test_fresh_db_loaddata_resolves_but_does_not_update_seeded_row(self) -> None:
        """#946/#2266: NaturalKeyMixin makes ``loaddata`` resolve-not-duplicate a
        pre-existing same-name row (no IntegrityError) — but it still can't UPDATE
        it. ``DecorationKind`` is a SharedMemoryModel; the identity map returns the
        already-cached seeded instance, so the content-authored description is
        silently dropped. This is the honest, documented no-op — ``load_entries``
        (covered by ``NewDomainContentLoadTests``) is the only update-safe path.
        """
        ensure_decoration_kinds()
        seeded = DecorationKind.objects.get(name="Great Hearth")
        seeded_description = seeded.description

        _write(self.root, "decoration_kinds/hearth.md", GOOD_DECORATION_KIND)
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        written = write_fixtures(build_all(self.root), Path(out.name))
        decoration_fixture = next(p for p in written if p.name == "content_decoration_kinds.json")

        # No IntegrityError on the unique `name` constraint: NaturalKeyMixin lets
        # loaddata resolve the existing row instead of blind-INSERTing a dupe.
        call_command("loaddata", str(decoration_fixture), verbosity=0)

        assert DecorationKind.objects.filter(name="Great Hearth").count() == 1
        seeded.refresh_from_db()
        # The content body ("A roaring stone hearth...") never lands — loaddata
        # on an idmapper model cannot UPDATE (#946). Still the seeded PLACEHOLDER.
        assert seeded.description == seeded_description
        assert "roaring stone hearth" not in seeded.description


class NewDomainContentLoadTests(TestCase):
    """#2266: create-then-update idempotency by natural key, per new domain."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        OrganizationFactory(name="Builders Guild")

    def test_npc_role_load_creates_then_updates(self) -> None:
        _write(self.root, "npc_roles/clerk.md", GOOD_NPC_ROLE)
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        role = NPCRole.objects.get(name="Builders Guild Clerk")
        assert role.faction_affiliation.name == "Builders Guild"
        assert role.default_rapport_starting_value == 5

        _write(
            self.root,
            "npc_roles/clerk.md",
            GOOD_NPC_ROLE.replace(
                "Issues building permits on behalf of the Builders Guild.",
                "Rewritten flavor text.",
            ),
        )
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)
        assert NPCRole.objects.filter(name="Builders Guild Clerk").count() == 1
        role.refresh_from_db()
        assert role.description == "Rewritten flavor text."

    def test_npc_role_omitted_optional_key_leaves_existing_value_on_update(self) -> None:
        """#2266 Q1/review fix: three-state convention, "absent" branch — an omitted
        optional key (including ``faction_affiliation``) doesn't clobber the row on
        UPDATE. Contrast with the "explicit null" branch covered by
        ``test_npc_role_explicit_null_faction_clears_it_on_update`` below.
        """
        _write(self.root, "npc_roles/clerk.md", GOOD_NPC_ROLE)
        load_entries(build_all(self.root))
        role = NPCRole.objects.get(name="Builders Guild Clerk")
        assert role.default_rapport_starting_value == 5

        # Re-author without default_rapport_starting_value or faction_affiliation.
        _write(
            self.root,
            "npc_roles/clerk.md",
            "---\nname: Builders Guild Clerk\n---\nRewritten flavor text.\n",
        )
        load_entries(build_all(self.root))
        role.refresh_from_db()
        assert role.description == "Rewritten flavor text."
        assert role.default_rapport_starting_value == 5
        assert role.faction_affiliation.name == "Builders Guild"

    def test_npc_role_explicit_null_faction_clears_it_on_update(self) -> None:
        """#2266 review fix: three-state convention, "explicit null" branch — a
        frontmatter key PRESENT but null/empty clears the FK, distinct from the
        "absent" branch above which leaves it untouched. Without this distinction,
        faction_affiliation would be one-way-sticky (content could set it but never
        un-set it).
        """
        _write(self.root, "npc_roles/clerk.md", GOOD_NPC_ROLE)
        load_entries(build_all(self.root))
        role = NPCRole.objects.get(name="Builders Guild Clerk")
        assert role.faction_affiliation.name == "Builders Guild"

        _write(
            self.root,
            "npc_roles/clerk.md",
            "---\nname: Builders Guild Clerk\nfaction_affiliation:\n---\nRewritten flavor text.\n",
        )
        load_entries(build_all(self.root))
        role.refresh_from_db()
        assert role.faction_affiliation is None
        assert role.description == "Rewritten flavor text."

    def test_item_template_load_creates_then_updates(self) -> None:
        _write(self.root, "items/longsword.md", GOOD_ITEM)
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        item = ItemTemplate.objects.get(name="Iron Longsword")
        assert item.value == 40

        _write(self.root, "items/longsword.md", GOOD_ITEM.replace("well-balanced", "battered"))
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)
        assert ItemTemplate.objects.filter(name="Iron Longsword").count() == 1

    def test_building_kind_load_creates_then_updates(self) -> None:
        _write(self.root, "building_kinds/watchtower.md", GOOD_BUILDING_KIND)
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (1, 0)
        assert BuildingKind.objects.filter(name="Watchtower").count() == 1

        _write(
            self.root,
            "building_kinds/watchtower.md",
            GOOD_BUILDING_KIND.replace("fortified lookout post", "watchpost"),
        )
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)
        assert BuildingKind.objects.filter(name="Watchtower").count() == 1

    def test_decoration_kind_seeder_row_superseded_by_content(self) -> None:
        """The seeder-name-mismatch bug this issue fixes stays fixed.

        Seeds the real DecorationKind row (post-rename), then loads authored
        content for the same name — must UPDATE that row, never create a
        second orphaned one.
        """
        ensure_decoration_kinds()
        assert DecorationKind.objects.filter(name="Great Hearth").count() == 1

        _write(self.root, "decoration_kinds/hearth.md", GOOD_DECORATION_KIND)
        created, updated = load_entries(build_all(self.root))
        assert (created, updated) == (0, 1)

        assert DecorationKind.objects.filter(name="Great Hearth").count() == 1
        kind = DecorationKind.objects.get(name="Great Hearth")
        assert kind.description == "A roaring stone hearth that drives out the worst of the cold."


class ResolveNaturalKeyFieldsGuardTests(TestCase):
    """#2266 review fix: ``_resolve_natural_key_fields`` must not crash on a
    list-valued value for a NON-relational field — it should raise a clean
    ContentError instead of a bare AttributeError from ``related_model``.
    """

    def test_non_relational_list_field_raises_content_error(self) -> None:
        # NPCRole.description is a plain TextField (not a relation); a list
        # value there can only mean a future bug, not a legitimate FK-by-name.
        with self.assertRaises(ContentError) as ctx:
            _resolve_natural_key_fields(NPCRole, {"description": ["oops"]}, None)
        assert "description" in str(ctx.exception)

    def test_relational_list_field_still_resolves(self) -> None:
        # Sanity check the guard doesn't break the legitimate FK-by-name path.
        OrganizationFactory(name="Builders Guild")
        fields = {"faction_affiliation": ["Builders Guild"]}
        _resolve_natural_key_fields(NPCRole, fields, None)
        assert fields["faction_affiliation"].name == "Builders Guild"
