"""Tests for the tradition membership lifecycle (#2441 Task 8)."""

from django.db import IntegrityError
from django.test import TestCase
import pytest

from world.character_creation.factories import BeginningTraditionFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.exceptions import AlreadyInTraditionError, NoActiveTraditionError
from world.magic.factories import (
    CharacterTechniqueFactory,
    CharacterTraditionFactory,
    TraditionFactory,
)
from world.magic.models import CharacterTradition
from world.magic.services.tradition_membership import join_tradition, leave_tradition


class JoinTraditionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.unbound = TraditionFactory(name="Unbound")
        self.caretakers = TraditionFactory(name="The Caretakers")

    def test_first_join_creates_active_row(self) -> None:
        row = join_tradition(self.sheet, self.unbound)

        assert row.tradition == self.unbound
        assert row.left_at is None
        assert self.sheet.character_traditions.filter(left_at__isnull=True).count() == 1

    def test_join_swaps_active_row_with_history(self) -> None:
        old = CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)

        new_row = join_tradition(self.sheet, self.caretakers)

        old.refresh_from_db()
        assert old.left_at is not None
        assert new_row.tradition == self.caretakers
        assert new_row.left_at is None
        assert self.sheet.character_traditions.count() == 2
        active = self.sheet.character_traditions.get(left_at__isnull=True)
        assert active.pk == new_row.pk

    def test_noop_rejoin_raises(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)

        with pytest.raises(AlreadyInTraditionError):
            join_tradition(self.sheet, self.unbound)

    def test_join_removes_unbound_and_orphaned_drawbacks_for_living_tradition(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)
        unbound_drawback = DistinctionFactory(slug="unbound", cost_per_rank=-2)
        orphaned_drawback = DistinctionFactory(slug="orphaned-tradition", cost_per_rank=-2)
        CharacterDistinctionFactory(
            character=self.sheet,
            distinction=unbound_drawback,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )
        CharacterDistinctionFactory(
            character=self.sheet,
            distinction=orphaned_drawback,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )

        join_tradition(self.sheet, self.caretakers)

        assert not CharacterDistinction.objects.filter(
            character=self.sheet, distinction=unbound_drawback
        ).exists()
        assert not CharacterDistinction.objects.filter(
            character=self.sheet, distinction=orphaned_drawback
        ).exists()

    def test_join_tolerates_absent_drawback_rows(self) -> None:
        """Neither slug seeded yet (e.g. Task 9 not run) — join must not error."""
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)

        # Should not raise even though no Distinction with either slug exists.
        join_tradition(self.sheet, self.caretakers)

        assert self.sheet.character_traditions.filter(
            tradition=self.caretakers, left_at__isnull=True
        ).exists()

    def test_join_orphaned_tradition_keeps_drawback(self) -> None:
        orphaned_drawback = DistinctionFactory(slug="orphaned-tradition", cost_per_rank=-2)
        metallic_order = TraditionFactory(name="Metallic Order")
        BeginningTraditionFactory(
            tradition=metallic_order,
            required_distinction=orphaned_drawback,
        )
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)
        CharacterDistinctionFactory(
            character=self.sheet,
            distinction=orphaned_drawback,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )

        join_tradition(self.sheet, metallic_order)

        assert CharacterDistinction.objects.filter(
            character=self.sheet, distinction=orphaned_drawback
        ).exists()

    def test_learned_techniques_untouched_on_join(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)
        technique_link = CharacterTechniqueFactory(character=self.sheet)

        join_tradition(self.sheet, self.caretakers)

        assert technique_link.__class__.objects.filter(pk=technique_link.pk).exists()


class LeaveTraditionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.tradition = TraditionFactory()

    def test_leave_sets_left_at_no_replacement_row(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.tradition)

        ended = leave_tradition(self.sheet)

        assert ended.left_at is not None
        assert self.sheet.character_traditions.filter(left_at__isnull=True).count() == 0
        assert self.sheet.character_traditions.count() == 1

    def test_leave_with_no_active_tradition_raises(self) -> None:
        with pytest.raises(NoActiveTraditionError):
            leave_tradition(self.sheet)

    def test_leave_reapplies_unbound_when_seeded(self) -> None:
        DistinctionFactory(slug="unbound", cost_per_rank=-2)
        CharacterTraditionFactory(character=self.sheet, tradition=self.tradition)

        leave_tradition(self.sheet)

        grant = CharacterDistinction.objects.filter(
            character=self.sheet, distinction__slug="unbound"
        ).first()
        assert grant is not None
        assert grant.origin == DistinctionOrigin.GAMEPLAY

    def test_leave_skips_reapply_when_unbound_not_seeded(self) -> None:
        CharacterTraditionFactory(character=self.sheet, tradition=self.tradition)

        # Must not raise even though no "unbound" Distinction row exists.
        leave_tradition(self.sheet)

        assert not CharacterDistinction.objects.filter(
            character=self.sheet, distinction__slug="unbound"
        ).exists()


class ActiveTraditionConstraintTests(TestCase):
    def test_constraint_blocks_two_active_rows(self) -> None:
        sheet = CharacterSheetFactory()
        t1 = TraditionFactory(name="Tradition A")
        t2 = TraditionFactory(name="Tradition B")
        CharacterTradition.objects.create(character=sheet, tradition=t1)

        with pytest.raises(IntegrityError):
            CharacterTradition.objects.create(character=sheet, tradition=t2)


class OrgMembershipTriggersJoinTests(TestCase):
    """Accepting membership in a tradition's teaching org triggers join_tradition
    (#2441 ruling 1)."""

    def test_accept_invitation_joins_tradition(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.membership_services import (
            accept_invitation,
            active_membership_for_persona,
            invite_to_organization,
            join_organization,
        )

        tradition = TraditionFactory()
        org = OrganizationFactory(tradition=tradition)
        manager = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

        manager_membership = join_organization(org, manager)
        manager_membership.rank = org.ranks.get(tier=1)
        manager_membership.save()

        invite = invite_to_organization(org, manager, member)
        accept_invitation(invite, member)

        assert member.character_sheet.character_traditions.filter(
            tradition=tradition, left_at__isnull=True
        ).exists()
        assert active_membership_for_persona(org, member) is not None

    def test_accept_invitation_no_tradition_org_does_not_touch_tradition(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.membership_services import (
            accept_invitation,
            invite_to_organization,
            join_organization,
        )

        org = OrganizationFactory(tradition=None)
        manager = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

        manager_membership = join_organization(org, manager)
        manager_membership.rank = org.ranks.get(tier=1)
        manager_membership.save()

        invite = invite_to_organization(org, manager, member)
        accept_invitation(invite, member)

        assert not member.character_sheet.character_traditions.exists()
