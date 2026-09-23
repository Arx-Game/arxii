"""Staff Almanach de Catenys actions (#3983): the feudal ladder + house record.

Ten REGISTRY actions, all ``category="almanach"``, ``target_type=SELF``, gated
by ``StaffOnlyPrerequisite`` — the shared ``action.run()`` seam a future web
staff console and telnet alike will dispatch through, mirroring the shape of
the world-builder canvas (``world_builder.py``). Each is a thin wrapper over
``world.societies.houses.almanach`` (rungs, house record, demesne, estate,
household, public belief), ``world.societies.houses.services`` (fealty,
holdings), and — for ``almanach_edit_kin`` — the kinship writers in
``world.roster.services.kinship``. Every refusal is a plain
``ActionResult(success=False, message=...)`` sourced from a service's
``HousesServiceError``/``KinshipServiceError`` ``user_message`` or a locally
composed sentence, never ``str(exc)``. Every success carries the
created/touched rows' ids in ``data`` so a caller can chain a follow-up call
(e.g. name a freshly planted rung) without a refetch.

``almanach_edit_kin`` deliberately does NOT preset the freshly created
``Kinsperson.family`` to the house's family at creation time, even though its
kwargs mirror ``HouseClaimKin`` field-for-field: ``Kinsperson.family`` is
documented as a denorm "maintained by the membership services"
(``world/roster/models/families.py``), and ``acknowledge_into_family`` (the
``recognize_birth`` fallback for the ``child`` relation) refuses outright
when the child already carries the target family — presetting it would make
every child-relation call whose realm has no matching
``HouseRecognitionRule`` refuse itself. The relation-specific service calls
(``record_parentage`` + ``recognize_birth``/``acknowledge_into_family`` for
``child``; ``record_union`` + ``add_membership`` for ``spouse``;
``add_membership`` directly for ``head``) are the sole writers of ``family``,
exactly as they already are for every other caller of those services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite, StaffOnlyPrerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NO_SUCH_HOUSE = "No such house."


@dataclass
class _AlmanachAction(Action):
    """Shared shape for the staff Almanach de Catenys verbs (#3983)."""

    category: str = "almanach"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [StaffOnlyPrerequisite()]


@dataclass
class AlmanachPlantRungAction(_AlmanachAction):
    """Plant a rung (and its seat chain) under an optional parent title.

    Kwargs: ``realm_id``, ``tier``, ``name`` (blank plants an unnamed rung),
    optional ``parent_title_id``, optional ``held_by_org_id``.
    """

    key: str = "almanach_plant_rung"
    name: str = "Plant Rung"
    icon: str = "flag"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.realms.models import Realm  # noqa: PLC0415
        from world.societies.houses.almanach import plant_rung  # noqa: PLC0415
        from world.societies.houses.constants import TitleTier  # noqa: PLC0415
        from world.societies.houses.models import Title  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        realm = Realm.objects.filter(pk=kwargs.get("realm_id")).first()
        if realm is None:
            return ActionResult(success=False, message="No such realm.")
        tier = (kwargs.get("tier") or "").strip()
        if tier not in TitleTier.values:
            options = ", ".join(TitleTier.values)
            return ActionResult(success=False, message=f"No '{tier}' tier. Options: {options}.")
        parent_title_id = kwargs.get("parent_title_id")
        parent_title = None
        if parent_title_id:
            parent_title = Title.objects.filter(pk=parent_title_id).first()
            if parent_title is None:
                return ActionResult(success=False, message="No such parent title.")
        held_by_org_id = kwargs.get("held_by_org_id")
        held_by = None
        if held_by_org_id:
            held_by = Organization.objects.filter(pk=held_by_org_id).first()
            if held_by is None:
                return ActionResult(success=False, message=_NO_SUCH_HOUSE)
        rung_name = (kwargs.get("name") or "").strip()
        try:
            title = plant_rung(
                realm=realm, tier=tier, name=rung_name, parent_title=parent_title, held_by=held_by
            )
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{title.name or 'An unnamed rung'} planted (title #{title.pk}).",
            data={"title_id": title.pk},
        )


@dataclass
class AlmanachBatchUnclaimedAction(_AlmanachAction):
    """Plant a batch of unclaimed rungs under a parent title.

    Kwargs: ``parent_title_id``, ``tier``, ``count``, optional
    ``baronies_per_county``.
    """

    key: str = "almanach_batch_unclaimed"
    name: str = "Batch Plant Unclaimed Rungs"
    icon: str = "flag"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.almanach import batch_unclaimed  # noqa: PLC0415
        from world.societies.houses.constants import TitleTier  # noqa: PLC0415
        from world.societies.houses.models import Title  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        parent_title = Title.objects.filter(pk=kwargs.get("parent_title_id")).first()
        if parent_title is None:
            return ActionResult(success=False, message="No such parent title.")
        tier = (kwargs.get("tier") or "").strip()
        if tier not in TitleTier.values:
            options = ", ".join(TitleTier.values)
            return ActionResult(success=False, message=f"No '{tier}' tier. Options: {options}.")
        try:
            count = int(kwargs["count"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(success=False, message="Pick a count.")
        if count < 1:
            return ActionResult(success=False, message="Pick a count.")
        try:
            baronies_per_county = int(kwargs.get("baronies_per_county") or 0)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Baronies per county must be a number.")
        try:
            titles = batch_unclaimed(
                parent_title=parent_title,
                tier=tier,
                count=count,
                baronies_per_county=baronies_per_county,
            )
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{len(titles)} unclaimed rung(s) planted.",
            data={"title_ids": [t.pk for t in titles]},
        )


@dataclass
class AlmanachNameRungAction(_AlmanachAction):
    """Name (or rename) a rung. Kwargs: ``title_id``, ``name``."""

    key: str = "almanach_name_rung"
    name: str = "Name Rung"
    icon: str = "flag"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.almanach import name_rung  # noqa: PLC0415
        from world.societies.houses.models import Title  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        title = Title.objects.filter(pk=kwargs.get("title_id")).first()
        if title is None:
            return ActionResult(success=False, message="No such title.")
        rung_name = (kwargs.get("name") or "").strip()
        if not rung_name:
            return ActionResult(success=False, message="Name the rung.")
        try:
            title = name_rung(title, rung_name)
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{title.name} named.",
            data={"title_id": title.pk},
        )


@dataclass
class AlmanachEditHouseAction(_AlmanachAction):
    """Edit a house's charter record and identity facets.

    Kwargs: ``org_id``, optional ``name``/``words``/``colors``/
    ``sigil_description``/``description`` (absent leaves untouched),
    optional ``house_state``, optional ``default_succession_law_id`` (falsy
    clears it), and optional ``aspect_option_ids``/``feature_ids`` lists —
    each, when present (even ``[]``), REPLACES the house's
    ``OrganizationAspect``/``OrganizationFeature`` rows wholesale (#3983
    Decision 4).
    """

    key: str = "almanach_edit_house"
    name: str = "Edit House"
    icon: str = "shield"

    def execute(  # noqa: C901, PLR0912 — one straight-line field-by-field editor
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db import transaction  # noqa: PLC0415

        from world.societies.houses.constants import HouseState  # noqa: PLC0415
        from world.societies.houses.models import (  # noqa: PLC0415
            HouseAspectOption,
            HouseFeature,
            OrganizationAspect,
            OrganizationFeature,
            SuccessionLaw,
        )
        from world.societies.models import Organization  # noqa: PLC0415

        org = Organization.objects.filter(pk=kwargs.get("org_id")).first()
        if org is None:
            return ActionResult(success=False, message=_NO_SUCH_HOUSE)

        # Resolve and validate EVERYTHING before the first write below — a
        # bare ``return`` inside ``transaction.atomic()`` does not roll it
        # back (only a propagating exception does), so a validation failure
        # discovered after a write would silently commit a partial edit.
        update_fields = []
        for field in ("name", "words", "colors", "sigil_description", "description"):
            if kwargs.get(field) is not None:
                setattr(org, field, kwargs[field])
                update_fields.append(field)
        house_state = kwargs.get("house_state")
        if house_state is not None:
            if house_state not in HouseState.values:
                options = ", ".join(HouseState.values)
                return ActionResult(
                    success=False, message=f"No '{house_state}' house state. Options: {options}."
                )
            org.house_state = house_state
            update_fields.append("house_state")
        if "default_succession_law_id" in kwargs:  # noqa: STRING_LITERAL
            law_id = kwargs["default_succession_law_id"]
            law = None
            if law_id:
                law = SuccessionLaw.objects.filter(pk=law_id).first()
                if law is None:
                    return ActionResult(success=False, message="No such succession law.")
            org.default_succession_law = law
            update_fields.append("default_succession_law")

        aspect_options = None
        aspect_option_ids = kwargs.get("aspect_option_ids")
        if aspect_option_ids is not None:
            aspect_options = list(HouseAspectOption.objects.filter(pk__in=aspect_option_ids))
            if len(aspect_options) != len(set(aspect_option_ids)):
                return ActionResult(
                    success=False, message="One of those house aspects doesn't exist."
                )

        features = None
        feature_ids = kwargs.get("feature_ids")
        if feature_ids is not None:
            features = list(HouseFeature.objects.filter(pk__in=feature_ids))
            if len(features) != len(set(feature_ids)):
                return ActionResult(
                    success=False, message="One of those house features doesn't exist."
                )

        with transaction.atomic():
            if update_fields:
                org.save(update_fields=update_fields)
            if aspect_options is not None:
                OrganizationAspect.objects.filter(organization=org).delete()
                OrganizationAspect.objects.bulk_create(
                    OrganizationAspect(
                        organization=org, definition_id=opt.definition_id, option=opt
                    )
                    for opt in aspect_options
                )
            if features is not None:
                OrganizationFeature.objects.filter(organization=org).delete()
                OrganizationFeature.objects.bulk_create(
                    OrganizationFeature(organization=org, feature=feature) for feature in features
                )
        return ActionResult(success=True, message=f"{org.name} updated.", data={"org_id": org.pk})


@dataclass
class AlmanachSwearAction(_AlmanachAction):
    """Bind a house's fealty to a liege by staff fiat.

    Kwargs: ``vassal_org_id``, ``liege_org_id``, optional ``tithe_pct``
    (omitted uses the realm default, #3983 Decision 2).
    """

    key: str = "almanach_swear"
    name: str = "Swear Fealty"
    icon: str = "shield"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.services import (  # noqa: PLC0415
            HousesServiceError,
            swear_fealty,
        )
        from world.societies.models import Organization  # noqa: PLC0415

        vassal = Organization.objects.filter(pk=kwargs.get("vassal_org_id")).first()
        if vassal is None:
            return ActionResult(success=False, message="No such vassal house.")
        liege = Organization.objects.filter(pk=kwargs.get("liege_org_id")).first()
        if liege is None:
            return ActionResult(success=False, message="No such liege house.")
        tithe_pct = kwargs.get("tithe_pct")
        if tithe_pct is not None:
            try:
                tithe_pct = int(tithe_pct)
            except (TypeError, ValueError):
                return ActionResult(success=False, message="Tithe must be a whole percent.")
        try:
            swear_fealty(vassal=vassal, liege=liege, tithe_pct=tithe_pct)
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{vassal.name} swears fealty to {liege.name}.",
            data={"vassal_org_id": vassal.pk, "liege_org_id": liege.pk},
        )


@dataclass
class AlmanachDescribeDemesneAction(_AlmanachAction):
    """Write a demesne's public description, hall, and land shapes.

    Kwargs: ``domain_id``, ``description``, ``hall_name``,
    ``land_shape_names`` (list of names).
    """

    key: str = "almanach_describe_demesne"
    name: str = "Describe Demesne"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.almanach import describe_demesne  # noqa: PLC0415
        from world.societies.houses.models import Domain  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        domain = Domain.objects.filter(pk=kwargs.get("domain_id")).first()
        if domain is None:
            return ActionResult(success=False, message="No such demesne.")
        land_shape_names = list(kwargs.get("land_shape_names") or [])
        try:
            domain = describe_demesne(
                domain=domain,
                description=kwargs.get("description") or "",
                hall_name=(kwargs.get("hall_name") or "").strip(),
                land_shape_names=land_shape_names,
            )
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{domain.name or 'The demesne'} described.",
            data={"domain_id": domain.pk},
        )


@dataclass
class AlmanachAddHoldingAction(_AlmanachAction):
    """Attach a working holding to a demesne.

    Kwargs: ``domain_id``, ``holding_kind_id``, optional ``name``.
    """

    key: str = "almanach_add_holding"
    name: str = "Add Holding"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.models import Domain, HoldingKind  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError, add_holding  # noqa: PLC0415

        domain = Domain.objects.filter(pk=kwargs.get("domain_id")).first()
        if domain is None:
            return ActionResult(success=False, message="No such demesne.")
        kind = HoldingKind.objects.filter(pk=kwargs.get("holding_kind_id")).first()
        if kind is None:
            return ActionResult(success=False, message="No such holding kind.")
        try:
            holding = add_holding(domain=domain, kind=kind, name=(kwargs.get("name") or "").strip())
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{holding.name} added to {domain.name or 'the demesne'}.",
            data={"domain_id": domain.pk, "holding_id": holding.pk},
        )


@dataclass
class AlmanachPlanEstateAction(_AlmanachAction):
    """Plant a house's estate Area under a city (or a named district).

    Kwargs: ``org_id``, ``city_area_id``, ``name``, ``description``,
    optional ``district_area_id``.
    """

    key: str = "almanach_plan_estate"
    name: str = "Plan Estate"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.models import Area  # noqa: PLC0415
        from world.societies.houses.almanach import plan_estate  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        house = Organization.objects.filter(pk=kwargs.get("org_id")).first()
        if house is None:
            return ActionResult(success=False, message=_NO_SUCH_HOUSE)
        city_area = Area.objects.filter(pk=kwargs.get("city_area_id")).first()
        if city_area is None:
            return ActionResult(success=False, message="No such city.")
        district_area_id = kwargs.get("district_area_id")
        district = None
        if district_area_id:
            district = Area.objects.filter(pk=district_area_id).first()
            if district is None:
                return ActionResult(success=False, message="No such district.")
        estate_name = (kwargs.get("name") or "").strip()
        if not estate_name:
            return ActionResult(success=False, message="Name the estate.")
        estate = plan_estate(
            house=house,
            city_area=city_area,
            name=estate_name,
            description=kwargs.get("description") or "",
            district=district,
        )
        return ActionResult(
            success=True,
            message=f"{estate.name} planned for {house.name}.",
            data={"area_id": estate.pk, "org_id": house.pk},
        )


_KIN_UPDATE_ONLY_MESSAGE = (
    "Editing an existing kinsperson only changes name, gender, age, deceased "
    "status, and public belief — start a new entry to change relation, marriage, "
    "or family membership."
)

# Kwargs that mint a relation side effect (parentage/union/membership/household
# retainer) — refused outright alongside ``kinsperson_id`` (#3983 review fix 1):
# an update only ever touches the plain fields below.
_KIN_RELATION_ONLY_KWARGS = (
    "relation",
    "parent_kinsperson_id",
    "spouse_kinsperson_id",
    "born_into_family_id",
)


@dataclass
class AlmanachEditKinAction(_AlmanachAction):
    """Author a new node of a house's family tree, or update an existing one.

    Kwargs: ``org_id``, ``name``, ``is_deceased``, ``believed_deceased``,
    optional ``gender_id``, optional ``age``.

    **Create** (``kinsperson_id`` absent) additionally reads ``relation``
    (``child``/``spouse``/``head``/other), optional ``parent_kinsperson_id``
    (``relation="child"``), optional ``spouse_kinsperson_id``
    (``relation="spouse"``), optional ``born_into_family_id`` (a secondary,
    non-primary BORN membership regardless of ``relation``), and
    ``is_household`` (household retainer instead of family — no family
    membership is written for these, #3983 Decision 1).

    **Update** (``kinsperson_id`` given) changes ONLY a plain field
    (name/gender_id/age/is_deceased/believed_deceased) whose kwarg was
    actually passed — an absent kwarg leaves the existing value untouched,
    and a ``gender_id`` passed as falsy (e.g. ``None``) still clears the
    gender: it's the kwarg's ABSENCE, not its value, that makes a field a
    no-op (#3983 Task 10 fold-in). Relation, marriage, membership and
    household side effects run exactly once, at creation, and never re-fire
    on a later edit (#3983 review fix 1: a second edit used to re-mint a
    ``ParentageEdge``/``Union``, or downgrade a ``head``'s FOUNDING
    membership to BORN). Passing any of ``relation``/``parent_kinsperson_id``/
    ``spouse_kinsperson_id``/``born_into_family_id`` alongside ``kinsperson_id``
    is refused, and so is a ``kinsperson_id`` whose ``family_id`` isn't this
    house's own family (#3983 Task 10 fold-in).
    """

    key: str = "almanach_edit_kin"
    name: str = "Edit Kin"
    icon: str = "family"

    def execute(  # noqa: C901, PLR0912, PLR0915 — one straight-line relation dispatch
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db import transaction  # noqa: PLC0415

        from world.character_sheets.models import Gender  # noqa: PLC0415
        from world.roster.models import Family, Kinsperson, UnionKind  # noqa: PLC0415
        from world.roster.services.kinship import KinshipServiceError  # noqa: PLC0415
        from world.seeds.kinship import MARRIAGE_KIND_NAME  # noqa: PLC0415
        from world.societies.houses.almanach import (  # noqa: PLC0415
            record_kin,
            record_public_belief,
        )
        from world.societies.houses.constants import ClaimKinRelation  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        house = Organization.objects.filter(pk=kwargs.get("org_id")).first()
        if house is None:
            return ActionResult(success=False, message=_NO_SUCH_HOUSE)
        if house.family_id is None:
            return ActionResult(success=False, message="That house has no family on record.")

        kinsperson_id = kwargs.get("kinsperson_id")
        if kinsperson_id:
            if any(kwargs.get(field) for field in _KIN_RELATION_ONLY_KWARGS):
                return ActionResult(success=False, message=_KIN_UPDATE_ONLY_MESSAGE)
            node = Kinsperson.objects.filter(pk=kinsperson_id).first()
            if node is None:
                return ActionResult(success=False, message="No such kinsperson.")
            if node.family_id != house.family_id:
                return ActionResult(
                    success=False, message="That kinsperson isn't part of this house's family."
                )
            # Resolve and validate EVERYTHING before the first write below —
            # each plain field changes ONLY when its kwarg was actually
            # passed (an absent kwarg is a no-op; a falsy ``gender_id`` that
            # WAS passed still clears the gender, #3983 Task 10 fold-in).
            new_gender = node.gender
            if "gender_id" in kwargs:  # noqa: STRING_LITERAL
                new_gender_id = kwargs["gender_id"]
                new_gender = None
                if new_gender_id:
                    new_gender = Gender.objects.filter(pk=new_gender_id).first()
                    if new_gender is None:
                        return ActionResult(success=False, message="No such gender.")
            new_age = node.age
            if "age" in kwargs:  # noqa: STRING_LITERAL
                new_age = kwargs["age"]
                if new_age is not None:
                    try:
                        new_age = int(new_age)
                    except (TypeError, ValueError):
                        return ActionResult(success=False, message="Age must be a number.")
            update_fields: list[str] = []
            with transaction.atomic():
                if "name" in kwargs:  # noqa: STRING_LITERAL
                    node.name = (kwargs.get("name") or "").strip()
                    update_fields.append("name")
                if "gender_id" in kwargs:  # noqa: STRING_LITERAL
                    node.gender = new_gender
                    update_fields.append("gender")
                if "age" in kwargs:  # noqa: STRING_LITERAL
                    node.age = new_age
                    update_fields.append("age")
                if "is_deceased" in kwargs:  # noqa: STRING_LITERAL
                    node.is_deceased = bool(kwargs["is_deceased"])
                    update_fields.append("is_deceased")
                if update_fields:
                    node.save(update_fields=update_fields)
                if "believed_deceased" in kwargs:  # noqa: STRING_LITERAL
                    record_public_belief(node, believed_deceased=bool(kwargs["believed_deceased"]))
            return ActionResult(
                success=True,
                message=f"{node.name or 'The kinsperson'} updated.",
                data={"kinsperson_id": node.pk, "org_id": house.pk},
            )

        kin_name = (kwargs.get("name") or "").strip()
        gender_id = kwargs.get("gender_id")
        gender = None
        if gender_id:
            gender = Gender.objects.filter(pk=gender_id).first()
            if gender is None:
                return ActionResult(success=False, message="No such gender.")
        age = kwargs.get("age")
        if age is not None:
            try:
                age = int(age)
            except (TypeError, ValueError):
                return ActionResult(success=False, message="Age must be a number.")
        is_deceased = bool(kwargs.get("is_deceased"))
        believed_deceased = bool(kwargs.get("believed_deceased"))

        relation = (kwargs.get("relation") or "").strip()

        # Resolve and validate EVERYTHING before the ``record_kin`` call below
        # — a bare ``return`` inside its own ``transaction.atomic()`` does
        # not roll it back (only a propagating exception does), so any check
        # found only mid-write would risk committing a partial write (e.g.
        # an orphan Kinsperson) alongside a reported failure.
        parent = spouse = marriage_kind = born_into_family = None
        if relation == ClaimKinRelation.CHILD:
            parent_id = kwargs.get("parent_kinsperson_id")
            parent = Kinsperson.objects.filter(pk=parent_id).first() if parent_id else None
            if parent is None:
                return ActionResult(success=False, message="Pick the child's parent.")
        elif relation == ClaimKinRelation.SPOUSE:
            spouse_id = kwargs.get("spouse_kinsperson_id")
            spouse = Kinsperson.objects.filter(pk=spouse_id).first() if spouse_id else None
            if spouse is None:
                return ActionResult(success=False, message="Pick the spouse.")
            marriage_kind = UnionKind.objects.filter(name=MARRIAGE_KIND_NAME).first()
            if marriage_kind is None:
                return ActionResult(
                    success=False, message="Marriage is not configured for this realm."
                )
        born_into_family_id = kwargs.get("born_into_family_id")
        if born_into_family_id:
            born_into_family = Family.objects.filter(pk=born_into_family_id).first()
            if born_into_family is None:
                return ActionResult(success=False, message="No such family.")

        try:
            node, vacancy = record_kin(
                house=house,
                name=kin_name,
                relation=relation,
                gender=gender,
                age=age,
                is_deceased=is_deceased,
                believed_deceased=believed_deceased,
                parent=parent,
                spouse=spouse,
                marriage_kind=marriage_kind,
                born_into=born_into_family,
                is_household=bool(kwargs.get("is_household")),
            )
        except (HousesServiceError, KinshipServiceError) as exc:
            return ActionResult(success=False, message=exc.user_message)

        data: dict[str, Any] = {"kinsperson_id": node.pk, "org_id": house.pk}
        if vacancy is not None:
            data["vacancy_id"] = vacancy.pk
        return ActionResult(
            success=True, message=f"{node.name or 'The kinsperson'} recorded.", data=data
        )


@dataclass
class AlmanachPublishAction(_AlmanachAction):
    """Publish (or unpublish) a house to the Almanach. Kwargs: ``org_id``, ``publish``."""

    key: str = "almanach_publish"
    name: str = "Publish House"
    icon: str = "shield"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.houses.almanach import publish_house, unpublish_house  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        org = Organization.objects.filter(pk=kwargs.get("org_id")).first()
        if org is None:
            return ActionResult(success=False, message=_NO_SUCH_HOUSE)
        if kwargs.get("publish"):
            org = publish_house(org)
            message = f"{org.name} published to the Almanach."
        else:
            org = unpublish_house(org)
            message = f"{org.name} pulled back to draft."
        return ActionResult(success=True, message=message, data={"org_id": org.pk})
