"""CovenantRole inherits AbstractSpecializedVariant (schema no-op refactor, #1578).

Structural guard: the refactor must change the *base class* of ``CovenantRole``
from ``SharedMemoryModel`` to ``AbstractSpecializedVariant`` (which itself
inherits ``SharedMemoryModel``), hoisting four duplicated columns
(``resonance``, ``unlock_thread_level``, ``discovery_achievement``,
``codex_entry``) onto the shared base. No behavior change — the proven
``resolve_effective_role`` + ``fire_subrole_discoveries`` paths are the
canary (see their existing test modules).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from world.covenants.models import CovenantRole
from world.magic.specialization.models import AbstractSpecializedVariant


class CovenantRoleSpecializationBaseTests(SimpleTestCase):
    """Guard: CovenantRole inherits the shared specialization base (#1578)."""

    def test_covenant_role_is_specialized_variant(self) -> None:
        """CovenantRole must subclass AbstractSpecializedVariant (the shared base)."""
        self.assertTrue(issubclass(CovenantRole, AbstractSpecializedVariant))

    def test_covenant_role_has_shared_columns(self) -> None:
        """The four hoisted columns persist (inherited, not redefined on the subclass)."""
        field_names = {f.name for f in CovenantRole._meta.get_fields()}
        self.assertIn("resonance", field_names)
        self.assertIn("unlock_thread_level", field_names)
        self.assertIn("discovery_achievement", field_names)
        self.assertIn("codex_entry", field_names)
        # The parent self-FK stays on CovenantRole (entity-specific).
        self.assertIn("parent_role", field_names)

    def test_covenant_role_resolves_variant_queryset_via_sub_roles(self) -> None:
        """_variant_queryset must query parent.sub_roles (CovenantRole's FK reverse),
        not the base default parent.variants — otherwise matching_variant /
        newly_crossed_variants (used by the future generalized ceremony) return [].
        """
        # The classmethod exists (inherited, possibly overridden) and is callable.
        self.assertTrue(hasattr(CovenantRole, "_variant_queryset"))
        self.assertTrue(callable(CovenantRole._variant_queryset))

    def test_covenant_role_implements_discovery_narrative(self) -> None:
        """discovery_narrative must be overridden (the base raises NotImplementedError)."""
        method = CovenantRole.discovery_narrative
        # The method on CovenantRole must NOT be the abstract base's implementation
        # (which raises NotImplementedError). Compare the underlying function.
        self.assertIsNot(method, AbstractSpecializedVariant.discovery_narrative)
