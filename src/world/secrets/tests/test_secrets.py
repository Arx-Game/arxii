"""Character Secrets — model invariant + authoring services (#1334, slice 1).

Bio/story stay public; sensitive facts live here. The load-bearing rule is
anchor-scales-with-level: only Level-1 player-flavor may be free-authored, so player flavor can
never masquerade as canon.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.missions.factories import MissionDeedRecordFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory
from world.secrets.constants import ACCUSATION_MAX_LEVEL, SecretLevel, SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.models import Secret, SecretKnowledge
from world.secrets.services import (
    SecretError,
    accusation_permitted,
    author_player_flavor_secret,
    author_secret,
    grant_secret_knowledge,
    mint_accusation,
    secret_known_to,
    secrets_explaining,
    set_secret_act_anchor,
)
from world.societies.factories import LegendEntryFactory


class SecretModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = CharacterSheetFactory()

    def test_gm_secret_may_sit_at_any_level(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.GM_AUTHORED,
            level=SecretLevel.DANGEROUS,
        )
        secret.full_clean()  # no raise
        assert secret.level == SecretLevel.DANGEROUS

    def test_action_anchored_secret_may_sit_at_any_level(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACTION_ANCHORED,
            level=SecretLevel.CAREFULLY_KEPT,
        )
        secret.full_clean()  # no raise

    def test_player_flavor_is_allowed_at_level_one(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
        )
        secret.full_clean()  # no raise

    def test_player_flavor_above_level_one_is_rejected(self) -> None:
        secret = SecretFactory.build(
            subject_sheet=self.subject,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            level=SecretLevel.DANGEROUS,
        )
        with self.assertRaises(ValidationError):
            secret.full_clean()

    def test_category_null_means_unknown(self) -> None:
        secret = SecretFactory(subject_sheet=self.subject, category=None)
        assert secret.category is None  # Unknown is a first-class state

    def test_a_secret_is_owned_by_exactly_one_subject(self) -> None:
        # Single-owner policy: a secret belongs to exactly one character (no shared/group rows).
        secret = SecretFactory(subject_sheet=self.subject)
        assert secret in self.subject.secrets.all()


class AuthorSecretServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = CharacterSheetFactory()
        cls.category = SecretCategoryFactory(name="Scandal")

    def test_author_secret_persists_a_valid_secret(self) -> None:
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.GM_AUTHORED,
            level=SecretLevel.DANGEROUS,
            content="She poisoned the duke.",
            category=self.category,
            consequences="Execution if proven.",
        )
        assert Secret.objects.filter(pk=secret.pk).exists()
        assert secret.category_id == self.category.pk

    def test_author_secret_rejects_player_flavor_above_level_one(self) -> None:
        with self.assertRaises(SecretError):
            author_secret(
                subject_sheet=self.subject,
                provenance=SecretProvenance.PLAYER_FLAVOR,
                level=SecretLevel.DANGEROUS,
                content="totally real, trust me",
            )

    def test_author_player_flavor_secret_caps_at_level_one(self) -> None:
        persona = self.subject.primary_persona
        secret = author_player_flavor_secret(
            subject_sheet=self.subject,
            author_persona=persona,
            content="Terrified of the color blue.",
        )
        assert secret.level == SecretLevel.UNCOMMON_KNOWLEDGE
        assert secret.provenance == SecretProvenance.PLAYER_FLAVOR
        assert secret.author_persona_id == persona.pk


class MintAccusationServiceTests(TestCase):
    """The player-facing frame-job author path (#1825)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.accuser = CharacterSheetFactory()
        cls.accuser_persona = cls.accuser.primary_persona
        cls.target = CharacterSheetFactory()

    def test_mints_an_accusation_about_the_target(self) -> None:
        secret = mint_accusation(
            accuser_persona=self.accuser_persona,
            subject_sheet=self.target,
            content="They took bribes from the enemy.",
            level=SecretLevel.WHISPERS,
        )
        assert secret.provenance == SecretProvenance.ACCUSATION
        assert secret.subject_sheet_id == self.target.pk
        assert secret.author_persona_id == self.accuser_persona.pk
        assert secret.level == SecretLevel.WHISPERS

    def test_rejects_self_framing(self) -> None:
        # An accusation is about someone else — the first mint path where subject != actor.
        with self.assertRaises(SecretError):
            mint_accusation(
                accuser_persona=self.accuser_persona,
                subject_sheet=self.accuser,
                content="framing myself?",
            )

    def test_rejects_level_over_the_placeholder_cap(self) -> None:
        assert SecretLevel.DANGEROUS > ACCUSATION_MAX_LEVEL
        with self.assertRaises(SecretError):
            mint_accusation(
                accuser_persona=self.accuser_persona,
                subject_sheet=self.target,
                content="the gravest of crimes, no evidence",
                level=SecretLevel.DANGEROUS,
            )

    def test_author_holds_knowledge_of_their_own_accusation(self) -> None:
        # #1825 counter-play (light smear): the framer knows what they minted, so a Level-1
        # accusation is immediately gossipable by them (`gossip plant`).
        author_entry = RosterEntryFactory()
        secret = mint_accusation(
            accuser_persona=author_entry.character_sheet.primary_persona,
            subject_sheet=self.target,
            content="They cheat at cards.",
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
        )
        assert secret_known_to(secret, author_entry) is True


class AccusationPermittedTests(TestCase):
    """The frame-job consent gate (#1825) — the target's ``hostile`` category decides."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.framer_tenure = RosterTenureFactory()
        cls.framer_sheet = cls.framer_tenure.roster_entry.character_sheet
        cls.target_tenure = RosterTenureFactory()
        cls.target_sheet = cls.target_tenure.roster_entry.character_sheet
        cls.hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)

    def test_npc_target_is_always_frameable(self) -> None:
        npc_sheet = CharacterSheetFactory()  # no active RosterTenure
        assert accusation_permitted(framer_sheet=self.framer_sheet, target_sheet=npc_sheet) is True

    def test_open_hostile_category_permits(self) -> None:
        # hostile defaults EVERYONE here → a stranger may frame the target.
        assert (
            accusation_permitted(framer_sheet=self.framer_sheet, target_sheet=self.target_sheet)
            is True
        )

    def test_locked_down_target_blocks_the_frame(self) -> None:
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile, mode=ConsentMode.ALLOWLIST
        )
        assert (
            accusation_permitted(framer_sheet=self.framer_sheet, target_sheet=self.target_sheet)
            is False
        )


class SecretKnowledgeServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.secret = SecretFactory()
        cls.knower = RosterEntryFactory()

    def test_grant_records_the_fact_layer(self) -> None:
        held = grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        assert isinstance(held, SecretKnowledge)
        assert held.knows_category is False  # extra layers stay locked until unlocked
        assert held.knows_consequences is False
        assert secret_known_to(self.secret, self.knower) is True

    def test_grant_is_idempotent_and_layers_are_monotonic(self) -> None:
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        # Unlock a layer; re-granting without it does NOT re-hide it.
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret, knows_category=True)
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        rows = SecretKnowledge.objects.filter(roster_entry=self.knower, secret=self.secret)
        assert rows.count() == 1
        held = rows.get()
        assert held.knows_category is True  # stayed unlocked

    def test_unknown_to_a_stranger(self) -> None:
        assert secret_known_to(self.secret, RosterEntryFactory()) is False


class SecretClueTargetTests(TestCase):
    """A secret is discovered through the clue loop: a SECRET clue grants its fact (#1334)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.secret = SecretFactory()
        cls.knower = RosterEntryFactory()

    def _secret_clue(self):
        from world.clues.constants import ClueTargetKind
        from world.clues.models import Clue

        return Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=self.secret,
            name="A torn love letter",
            description="Ink smudged, but the meaning is plain.",
        )

    def test_granting_a_secret_clue_target_teaches_the_secret(self) -> None:
        from world.clues.services import grant_clue_target, target_already_known

        clue = self._secret_clue()
        assert target_already_known(clue, self.knower) is False
        grant_clue_target(clue, self.knower)
        assert secret_known_to(self.secret, self.knower) is True
        assert target_already_known(clue, self.knower) is True


class SecretActAnchorTests(TestCase):
    """A secret anchors to the act it is the truth behind — one act, several records (#1573)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = CharacterSheetFactory()
        cls.knower = RosterEntryFactory()

    def test_unanchored_secret_is_not_act_anchored(self) -> None:
        secret = SecretFactory(subject_sheet=self.subject)
        assert secret.is_act_anchored is False

    def test_one_secret_holds_all_three_records_of_one_act(self) -> None:
        # The load-bearing invariant: Bob's legendary murder is ONE secret, not three. The public
        # legend, the mission deed, and the scene are co-facets of the *same* act, carried on the
        # single secret — never fragmented into a secret per record (which would confuse a knower).
        legend = LegendEntryFactory()
        deed = MissionDeedRecordFactory()
        scene = SceneFactory()
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACTION_ANCHORED,
            level=SecretLevel.DANGEROUS,
            content="The heroic duel was a cold murder.",
            legend_deed=legend,
            mission_deed=deed,
            scene=scene,
        )
        assert secret.is_act_anchored is True
        assert secret.legend_deed_id == legend.pk
        assert secret.mission_deed_id == deed.pk
        assert secret.scene_id == scene.pk
        # Exactly one Secret row for the act — the anti-fragmentation guarantee.
        assert Secret.objects.filter(subject_sheet=self.subject).count() == 1

    def test_anchored_secret_cannot_be_player_flavor(self) -> None:
        # An act-anchored secret is evidenced ("true because it happened"), so it can never be the
        # unverified player-flavor tier — even at Level 1.
        scene = SceneFactory()
        with self.assertRaises(SecretError):
            author_secret(
                subject_sheet=self.subject,
                provenance=SecretProvenance.PLAYER_FLAVOR,
                level=SecretLevel.UNCOMMON_KNOWLEDGE,
                content="it totally happened",
                scene=scene,
            )

    def test_accusation_is_exempt_from_player_flavor_caps(self) -> None:
        # #1825: a player-authored ACCUSATION is a false scandal *meant* to carry weight — it may
        # be any level AND anchor to an alleged deed, unlike PLAYER_FLAVOR. Its guard is the
        # consent gate at the mint action, not the model.
        scene = SceneFactory()
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACCUSATION,
            level=SecretLevel.DANGEROUS,
            content="They poisoned the Duke — everyone should know.",
            scene=scene,
        )
        assert secret.provenance == SecretProvenance.ACCUSATION
        assert secret.level == SecretLevel.DANGEROUS
        assert secret.is_act_anchored is True

    def test_accusation_needs_no_anchor(self) -> None:
        # An accusation may also stand unanchored (a bare claim) at any level.
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACCUSATION,
            level=SecretLevel.CAREFULLY_KEPT,
            content="I heard they took bribes.",
        )
        assert secret.is_act_anchored is False
        assert secret.level == SecretLevel.CAREFULLY_KEPT

    def test_set_secret_act_anchor_sets_then_clears(self) -> None:
        secret = SecretFactory(subject_sheet=self.subject, provenance=SecretProvenance.GM_AUTHORED)
        legend = LegendEntryFactory()
        set_secret_act_anchor(secret, legend_deed=legend)
        secret.refresh_from_db()
        assert secret.legend_deed_id == legend.pk
        # Passing no records resets the full anchor state (explicit, not a partial merge).
        set_secret_act_anchor(secret)
        secret.refresh_from_db()
        assert secret.is_act_anchored is False

    def test_secrets_explaining_is_gated_by_knowledge(self) -> None:
        legend = LegendEntryFactory()
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACTION_ANCHORED,
            level=SecretLevel.WHISPERS,
            content="the truth behind the tale",
            legend_deed=legend,
        )
        # A stranger who has not learned the secret sees nothing behind the public deed.
        assert not secrets_explaining(roster_entry=self.knower, legend_deed=legend).exists()
        # Once they hold the secret, the backlink surfaces it (the "vice-versa" direction).
        grant_secret_knowledge(roster_entry=self.knower, secret=secret)
        known = secrets_explaining(roster_entry=self.knower, legend_deed=legend)
        assert [row.secret_id for row in known] == [secret.pk]

    def test_secrets_explaining_with_no_record_is_empty(self) -> None:
        assert not secrets_explaining(roster_entry=self.knower).exists()
