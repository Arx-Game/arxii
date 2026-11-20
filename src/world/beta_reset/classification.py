"""Which character-linked tables the beta reset wipes, keeps, or has not been ruled on (#3055).

``SCOPE_TABLE`` in ``world.beta_reset.services`` is a hand-written list, so a new
play-state table is silently missed unless something forces a decision. This module is
that something. Every concrete model in the ``arxii`` app that has a foreign key,
one-to-one or many-to-many to a character anchor (``CharacterSheet``, ``RosterEntry``,
``RosterTenure`` or ``Persona``) must be in exactly one of three places:

1. **Wiped** — a ``SCOPE_TABLE`` model, or a model every row of which Django deletes by
   cascade from a wholesale-wiped table (``wiped_models()``).
2. **Kept with a stated reason** — ``KEPT_WITH_REASON``: structural identity, an
   account-level record the owner's rulings say survives, authored catalog content, or a
   value the progress-reset service restores in place.
3. **Awaiting a ruling** — ``UNDECIDED_AWAITING_RULING``: not wiped today, and not clearly
   authored or account-level. The maintainer rules on each; until then the wipe leaves
   them alone. Listing a model here is NOT a decision to keep it.

``world.beta_reset.tests.test_classification`` fails when a character-linked model is in
none of the three, so a new play-state table cannot be added without someone choosing.
It also checks the delete ordering (``protect_blockers()``).
"""

from __future__ import annotations

from django.apps import apps
from django.db.models import (
    CASCADE,
    PROTECT,
    RESTRICT,
    ForeignKey,
    ManyToManyField,
    Model,
    OneToOneField,
)

from world.beta_reset.services import SCOPE_TABLE

#: The models whose rows identify a character. A model pointing at any of these (directly,
#: so "one hop" from the character through its sheet, roster entry, tenure or persona) is
#: character-linked and must be classified.
CHARACTER_ANCHOR_MODEL_NAMES = ("CharacterSheet", "RosterEntry", "RosterTenure", "Persona")

APP_LABEL = "arxii"


def _notes(note: str, *names: str) -> dict[str, str]:
    return dict.fromkeys(names, note)


def _merge(*groups: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for group in groups:
        duplicated = merged.keys() & group.keys()
        if duplicated:
            msg = f"Model(s) classified twice in world/beta_reset/classification.py: {duplicated}"
            raise ValueError(msg)
        merged.update(group)
    return merged


#: Kept on purpose. Every value says why.
KEPT_WITH_REASON: dict[str, str] = _merge(
    _notes(
        "Structural identity of the character; cutover ends tenures and never deletes any of "
        "these rows.",
        "CharacterSheet",
        "Persona",
        "RosterEntry",
        "RosterTenure",
    ),
    _notes(
        "Account-level record that the cutover rulings say survives with the alpha account "
        "(kudos, blocks, mutes, friendships, the player's own data).",
        "Block",
        "Friendship",
        "KudosTransaction",
        "Mute",
        "PlayerData",
    ),
    _notes(
        "Derived value that the progress-reset service steps back from the provenance ledger "
        "rather than deleting.",
        "CharacterTraitValue",
        "CharacterClassLevel",
    ),
    _notes(
        "Character-creation record of who the character was made to be; no play path writes it.",
        "CharacterOriginSlot",
    ),
    _notes(
        "Staff-authored catalog row; a row with owner_sheet set is synthesized for one sheet "
        "and lives and dies with it.",
        "CheckType",
    ),
    _notes(
        "Materialized view over the legend ledger; refresh_legend_views() recomputes it after "
        "the wipe.",
        "CharacterLegendSummary",
        "PersonaLegendSummary",
    ),
)

#: Not wiped today and not clearly authored or account-level. Each value is a one-line
#: note on what the table holds. The maintainer rules on these; do not read a listing as
#: a decision to keep.
UNDECIDED_AWAITING_RULING: dict[str, str] = _merge(
    _notes(
        "Magic state with no origin field: anima pool, aura, resonances, threads, technique "
        "meters, manifestation, motif, ultimates, rituals and prepared texts.",
        "CharacterAnima",
        "CharacterAura",
        "CharacterResonance",
        "Thread",
        "TechniqueProgress",
        "TechniqueProgressWeekly",
        "CharacterManifestation",
        "Motif",
        "KnownUltimate",
        "CharacterTradition",
        "CharacterRitualKnowledge",
        "CharacterCrossingText",
        "CharacterSurgeText",
        "ComboLearning",
        "CharacterPact",
        "AnimaRitualPerformance",
    ),
    _notes(
        "Magic unlock, teaching and drafting rows (gift unlocks, weaving unlocks, offers, "
        "ghost tutelage, technique drafts).",
        "CharacterGiftUnlock",
        "CharacterThreadWeavingUnlock",
        "TechniqueTeachingOffer",
        "ThreadWeavingTeachingOffer",
        "CodexTeachingOffer",
        "GhostTutelage",
        "TechniqueDraft",
    ),
    _notes(
        "Pending magic offers and receipts of crossings, alterations, flourishes and redemptions.",
        "PendingAlteration",
        "MagicalAlterationEvent",
        "PendingAudereOffer",
        "PendingAudereMajoraOffer",
        "AudereMajoraCrossing",
        "PendingEntryFlourishOffer",
        "EntryFlourishRecord",
        "PresentationEndorsement",
        "PendingRitualEffect",
        "DriftConversionOffer",
        "FallRedemptionRecord",
        "DramaticMomentTag",
    ),
    _notes(
        "Appetite, feeding and Sineating state: upkeep receipts, feeding records, "
        "Sineating, rescues, settling rites, Primum sightings.",
        "AppetiteUpkeepReceipt",
        "FeedingRecord",
        "Sineating",
        "SoulTetherRescue",
        "SettlingRite",
        "PrimumSighting",
    ),
    _notes(
        "Partly wiped today: a row tied to a wiped parent (combat encounter, scene or "
        "legend deed) goes by cascade, a row with no such parent survives.",
        "Kindling",
        "PrimumCallUp",
        "Reflection",
        "PersonaTitle",
        "Keepsake",
        "NPCLoan",
        "CharacterModifier",
    ),
    _notes(
        "Ritual sessions, sanctum and portal records, reincarnation.",
        "RitualSession",
        "RitualSessionParticipant",
        "RitualAnimaContribution",
        "SanctumDetails",
        "SanctumPendingPayout",
        "PortalAnchor",
        "Reincarnation",
    ),
    _notes(
        "Catalog row that a character created; survives today with its creator set null, "
        "so an alpha player's invention outlives the reset.",
        "Gift",
        "Technique",
    ),
    _notes(
        "Progression balances and receipts with no ledger: XP balance, unlock receipts, "
        "path history, development points, weekly usage, stat-point and maturation spends "
        "(the per-character progress reset deletes the two spend tables, the global wipe "
        "does not).",
        "CharacterXP",
        "CharacterUnlock",
        "CharacterPathHistory",
        "DevelopmentPoints",
        "DevelopmentTransaction",
        "WeeklySkillUsage",
        "XPTransaction",
        "LevelStatPointSpend",
        "MaturationSpend",
        "PathIntent",
        "Nomination",
        "RandomSceneCompletion",
        "RandomSceneTarget",
        "CohortEnrollment",
        "DuranceTrainingSite",
        "CharacterSpecializationValue",
        "TrainingAllocation",
        "CharacterChallengeRecord",
        "CharacterEngagement",
        "SkillCourseEnrollment",
        "StatTracker",
    ),
    _notes(
        "Codex and clue knowledge: CharacterCodexKnowledge has no origin field to split a "
        "CG grant from a play payoff.",
        "CharacterCodexKnowledge",
        "CharacterClue",
    ),
    _notes(
        "Authored clue target. Deleting a Secret cascades to the clues that point at it, "
        "and a clue's pool entries, visions and answers block that delete.",
        "Clue",
    ),
    _notes(
        "Relationships between characters and the labels players declare for them.",
        "CharacterRelationship",
        "RelationshipLabel",
    ),
    _notes(
        "Worship standing, prayers, pledges, miracles, visions, shrines and temples.",
        "DevotionStanding",
        "FavorInvocation",
        "MiraclePerformance",
        "PendingAnswer",
        "PledgeDetails",
        "Prayer",
        "ShrineDetails",
        "TempleDedication",
        "Vision",
        "WorshipDeclaration",
        "WorshipGrant",
        "WorshipRitePerformance",
        "WorshippedBeing",
    ),
    _notes(
        "Character-bound body and condition state: vitals, fatigue, action points, "
        "conditions, carried bodies, captivity.",
        "CharacterVitals",
        "CarriedBody",
        "FatiguePool",
        "ActionPointPool",
        "ConditionInstance",
        "Captivity",
        "DreamwalkPresence",
    ),
    _notes(
        "Forms, alternate selves and appearance history.",
        "ActiveAlternateSelf",
        "AlternateSelf",
        "AppearanceChangeLog",
        "CharacterForm",
        "CharacterFormState",
        "CharacterKnownStyle",
        "PersonaTraitDescriptor",
        "TemporaryFormChange",
    ),
    _notes(
        "Companions, armies and military units a character owns or commands.",
        "Companion",
        "Army",
        "MilitaryUnit",
    ),
    _notes(
        "Item holdings, outfits, fashion, crafting, trade, markets and vault records.",
        "CachetWallet",
        "EquippedItem",
        "FashionPresentation",
        "FashionShowing",
        "ItemInstance",
        "MantleLevelClearance",
        "Outfit",
        "OwnershipEvent",
        "ReclamationClaim",
        "RecycleRequest",
        "ShowcaseState",
        "Style",
        "Trendsetter",
        "CharacterRecipeKnowledge",
        "MakeoverConsentRequest",
        "CraftingServiceOffer",
        "FinishingPass",
        "MarketSale",
        "MarketStall",
        "WareListing",
        "MaterialBucket",
        "OrgMaterialLedgerEntry",
        "OrgVaultEvent",
        "VaultHolding",
        "VaultTransit",
        "TradeItemStake",
        "TradeSession",
        "FoodTransfer",
    ),
    _notes(
        "Buildings, ships, room features, locations, instanced rooms and positions.",
        "Building",
        "BuildingConstructionDetails",
        "BuildingListing",
        "BuildingMaterial",
        "BuildingPermitDetails",
        "ShipConstructionDetails",
        "PreparedGround",
        "Trap",
        "VaultAccessEntry",
        "VaultDetails",
        "LocationOwnership",
        "LocationTenancy",
        "InstancedRoom",
        "PositionEdge",
        "Rampart",
    ),
    _notes(
        "Reputation, memberships, offices, appeals and legend contributions in societies, "
        "organisations and houses.",
        "CrownBid",
        "CrownVote",
        "LegendContribution",
        "LegendRecognitionEvidence",
        "OrgAppeal",
        "OrgAppealSignon",
        "OrganizationMembership",
        "OrganizationMembershipOffer",
        "OrganizationObligation",
        "OrganizationOffice",
        "OrganizationReputation",
        "Proclamation",
        "SocietyReputation",
        "StandingDeclaration",
        "DomainEdict",
        "OrgPact",
        "StatureShift",
        "TitleClaim",
        "ContributionRecord",
        "Contribution",
        "Project",
    ),
    _notes(
        "Covenant roles, pacts, mentor bonds and the covenants themselves.",
        "CharacterCovenantRole",
        "CourtPact",
        "Covenant",
        "MentorBond",
    ),
    _notes(
        "Stories, beats, stakes, bulletin posts and the GM tools that point at characters.",
        "AggregateBeatContribution",
        "Beat",
        "BeatCompletion",
        "BeatOpponentLine",
        "EpisodeResolution",
        "Stake",
        "StakeContractActivation",
        "Story",
        "StoryParticipation",
        "StoryProgress",
        "StoryProtectedSubject",
        "TableBulletinPost",
        "TableBulletinReply",
        "GMPrompt",
        "GMRosterInvite",
        "GMSummonOffer",
        "GMTableMembership",
        "StoryRoomGrant",
        "StoryNPCSettings",
    ),
    _notes(
        "Missions a character took part in and the rewards and cooldowns that followed.",
        "MissionDeedRecord",
        "MissionDeedRewardLine",
        "MissionGiverCooldown",
        "MissionInstance",
        "MissionInvite",
        "MissionOption",
        "MissionParticipant",
        "MissionRiskAcknowledgement",
    ),
    _notes(
        "NPC dealings: assignments, standing declarations, regard, preferences, cooldowns, "
        "functionaries, listener posts, org tasks.",
        "DistinctionRegardSeed",
        "ExpulsionBar",
        "Functionary",
        "NPCAssignment",
        "NPCRoleCooldown",
        "NpcPreference",
        "NpcRegard",
        "OfferCooldown",
        "OfferSummons",
        "RecordedProfile",
        "NPCAsset",
        "ListenerPost",
        "NpcTaskAptitude",
        "OrgTask",
        "TaskFulfillment",
    ),
    _notes(
        "Estates, wills and bequests.",
        "Bequest",
        "EstateClaim",
        "EstateSettlement",
        "Will",
        "WillExecutor",
        "JournalBequestGrant",
    ),
    _notes(
        "Events, ceremonies, voyages and tavern games a character took part in.",
        "EventCatering",
        "EventHost",
        "EventInvitation",
        "Ceremony",
        "CeremonyHonoree",
        "CeremonyOffering",
        "CeremonySpeech",
        "Coronation",
        "Voyage",
        "VoyageInvite",
        "VoyageParticipant",
        "GamblingLossLedger",
        "GameSeat",
        "GameSession",
    ),
    _notes(
        "Social and consent settings a player configured, and scene-adjacent rows that are "
        "not wiped: consent groups and lists, block contact flags, pose submissions, place "
        "presence, speaker queues.",
        "ConsentGroup",
        "ConsentGroupMember",
        "SocialConsentBlacklist",
        "SocialConsentPreference",
        "SocialConsentWhitelist",
        "BlockContactFlag",
        "PoseSubmission",
        "PlacePresence",
        "SpeakerQueue",
        "SpeakerQueueEntry",
        "PlayerBoundary",
        "TreasuredSubject",
        "CharacterEnemy",
    ),
    _notes(
        "Messages and mail: channels, missives, narrative deliveries, player mail.",
        "BoardPost",
        "ChannelMessage",
        "ChannelSubscription",
        "Missive",
        "NarrativeMessageDelivery",
        "PlayerMail",
    ),
    _notes(
        "Player submissions and staff-facing reports: bug reports, petitions, feedback, "
        "check proposals, player reports, system error reports.",
        "BugReport",
        "CheckProposal",
        "Petition",
        "PlayerFeedback",
        "PlayerReport",
        "SystemErrorReport",
        "SheetUpdateRequest",
    ),
    _notes(
        "Roster bookkeeping: applications, family graph, tenure photos and display settings.",
        "RosterApplication",
        "Kinsperson",
        "HiddenCharacterArt",
        "TenureDisplaySettings",
        "TenureMedia",
    ),
    _notes(
        "Character goals, consequence outcomes, justice notes and other character-bound records.",
        "CharacterGoal",
        "GoalJournal",
        "GoalRevision",
        "CharacterDistinctionOther",
        "CharacterStandoffProfile",
        "ConsequenceOutcome",
        "CharacterCrimeNote",
        "ExileDecree",
        "DuelChallenge",
    ),
)


#: PROTECT relations the wipe cannot satisfy today, as ``(source, field, target)`` model and
#: field names. Each is a row that authored or undecided content holds on a table the wipe
#: deletes. ``test_classification`` fails when this set and ``protect_blockers()`` differ, so
#: a new blocker has to be handled or listed here with a reason.
PROTECT_BLOCKERS_AWAITING_RULING: dict[tuple[str, str, str], str] = {
    (source, field, "Clue"): (
        "Wiping Secrets cascades to the Clues that target them; this row points at a clue "
        "and raises ProtectedError if it exists. Whether authored clues should survive a "
        "Secret wipe is unruled."
    )
    for source, field in (
        ("Answer", "fact_clue"),
        ("Answer", "follow_up_clue"),
        ("CluePoolEntry", "clue"),
        ("ClueRevealOfferDetails", "clue"),
        ("StakeRewardLine", "clue"),
        ("Vision", "clue"),
    )
}


def _anchor_models() -> set[type[Model]]:
    return {apps.get_model(APP_LABEL, name) for name in CHARACTER_ANCHOR_MODEL_NAMES}


def _own_models() -> list[type[Model]]:
    return [
        model
        for model in apps.get_app_config(APP_LABEL).get_models()
        if not model._meta.auto_created  # noqa: SLF001
    ]


def character_linked_models() -> set[type[Model]]:
    """Every concrete ``arxii`` model with a relation to a character anchor."""
    anchors = _anchor_models()
    linked: set[type[Model]] = set()
    for model in _own_models():
        for field in model._meta.get_fields():  # noqa: SLF001
            if (
                isinstance(field, ForeignKey | OneToOneField | ManyToManyField)
                and field.related_model in anchors
            ):
                linked.add(model)
    return linked


def _cascade_edges() -> list[tuple[type[Model], type[Model], bool]]:
    """``(child, parent, child_column_is_required)`` for every CASCADE relation."""
    return [
        (model, field.related_model, not field.null)
        for model in apps.get_models()
        for field in model._meta.get_fields()  # noqa: SLF001
        if isinstance(field, ForeignKey | OneToOneField)
        and field.remote_field.on_delete is CASCADE
        and isinstance(field.related_model, type)
    ]


def cascade_closure() -> set[type[Model]]:
    """The ``SCOPE_TABLE`` models plus every model Django may delete by cascade from them."""
    closure = {entry.model for entry in SCOPE_TABLE}
    edges = _cascade_edges()
    grew = True
    while grew:
        grew = False
        for child, parent, _required in edges:
            if parent in closure and child not in closure:
                closure.add(child)
                grew = True
    return closure


def wiped_models() -> set[type[Model]]:
    """Models whose every row the wipe deletes.

    A ``SCOPE_TABLE`` entry with no filter wipes its whole table. A model with a required
    CASCADE foreign key to a wiped model loses every row with it. A filtered entry
    (a provenance split) and a model reached only through a nullable foreign key lose
    some rows, so they are not in this set.
    """
    wiped = {entry.model for entry in SCOPE_TABLE if not entry.filter_kwargs}
    edges = _cascade_edges()
    grew = True
    while grew:
        grew = False
        for child, parent, required in edges:
            if required and parent in wiped and child not in wiped:
                wiped.add(child)
                grew = True
    return wiped


def classify_character_linked_models() -> dict[type[Model], list[str]]:
    """Map each character-linked model to the lists that hold it (should be exactly one)."""
    wiped = wiped_models()
    partly_wiped_by_scope = {
        entry.model for entry in SCOPE_TABLE if entry.filter_kwargs and not entry.unblocker_only
    }
    placement: dict[type[Model], list[str]] = {}
    for model in character_linked_models():
        lists: list[str] = []
        if model in wiped or model in partly_wiped_by_scope:
            lists.append("wiped")
        if model.__name__ in KEPT_WITH_REASON:
            lists.append("kept")
        if model.__name__ in UNDECIDED_AWAITING_RULING:
            lists.append("undecided")
        placement[model] = lists
    return placement


def protect_blockers() -> list[tuple[type[Model], str, type[Model]]]:
    """PROTECT/RESTRICT relations that would stop the wipe on real data.

    Returns ``(source, field_name, target)`` for each relation onto a model the wipe
    deletes (a ``SCOPE_TABLE`` model or one reached by cascade) where the source is
    neither deleted by the wipe, nor deleted earlier than the target. A blocker raises
    ``ProtectedError`` as soon as one source row exists.
    """
    first_delete = _first_delete_index()
    blockers: list[tuple[type[Model], str, type[Model]]] = []
    for model in apps.get_models():
        for field in model._meta.get_fields():  # noqa: SLF001
            if not isinstance(field, ForeignKey | OneToOneField):
                continue
            if field.remote_field.on_delete not in (PROTECT, RESTRICT):
                continue
            target = field.related_model
            if not isinstance(target, type) or target not in first_delete:
                continue
            source_index = first_delete.get(model)
            if source_index is None or source_index > first_delete[target]:
                blockers.append((model, field.name, target))
    return sorted(blockers, key=lambda row: (row[0].__name__, row[1]))


def _first_delete_index() -> dict[type[Model], int]:
    """For each model the wipe deletes, the position of the first ``SCOPE_TABLE`` step that does."""
    edges = _cascade_edges()
    first: dict[type[Model], int] = {}
    for index, entry in enumerate(SCOPE_TABLE):
        reached = {entry.model}
        grew = True
        while grew:
            grew = False
            for child, parent, _required in edges:
                if parent in reached and child not in reached:
                    reached.add(child)
                    grew = True
        for model in reached:
            first.setdefault(model, index)
    return first
