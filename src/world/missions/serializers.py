"""DRF serializers for the missions authoring API (Phase D).

D1 ships ``MissionTemplateSerializer`` (list + detail browse). Editor
CRUD serializers for nodes / options / routes / candidates / rewards
land in D2; giver-library serializers in D3; predicate-tree in D5.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from world.missions.constants import MissionStatus
from world.missions.models import (
    MissionCategory,
    MissionGiver,
    MissionGiverOffering,
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)


def _validate_name_unique_on_update(
    instance: object,
    queryset: object,
    value: str,
    label: str,
) -> str:
    """On UPDATE: reject names already taken by another row of the same model.

    On CREATE (instance is None): no-op. The serializer's create() override
    auto-suffixes collisions via next_available_name, so the CREATE path
    must let the value through unchanged.
    """
    if instance is None:
        return value
    if queryset.exclude(pk=instance.pk).filter(name=value).exists():  # type: ignore[union-attr]
        msg = f"A {label} with this name already exists."
        raise serializers.ValidationError(msg)
    return value


class MissionTemplateSerializer(serializers.ModelSerializer):
    """List + detail serializer for MissionTemplate browse.

    Read-only fields cover the authoring footprint: name, summary,
    epilogue, level band, risk tier, weighting, era association, scope,
    cooldown, reward-group rule, active flag, access tier, categories,
    availability rule.

    D4 access-tier flip: PATCHing ``access_tier=open`` runs through
    ``validate_access_tier`` below — if any attached giver is not
    ``is_publishable`` (no target FK), the flip is refused with the
    list of unready givers' names so the Studio can show "needs-work."
    """

    # Module-level constants — bare strings as field/error keys would
    # trip STRING_LITERAL pre-commit.
    _OPEN_TIER_VALUE = "open"
    _STAFF_ONLY_TIER_VALUE = "staff_only"

    class Meta:
        model = MissionTemplate
        fields = [
            "id",
            "name",
            "summary",
            "epilogue",
            "level_band_min",
            "level_band_max",
            "risk_tier",
            "base_weight",
            "created_in_era",
            "arc_scope",
            "percent_replace",
            "cooldown",
            "reward_group_rule",
            "is_active",
            "access_tier",
            "categories",
            "availability_rule",
        ]
        read_only_fields = ["id"]
        # Suppress DRF's auto-generated UniqueValidator on ``name``.
        # The create() override calls next_available_name() to resolve
        # collisions via auto-suffix before the DB write, so a
        # UniqueValidator firing before create() would block that logic.
        extra_kwargs = {"name": {"validators": []}}

    def validate_name(self, value: str) -> str:
        """On UPDATE: reject names already taken by another template.

        On CREATE: ``create()`` calls ``next_available_name`` to auto-suffix
        collisions, so this validator returns the value unchanged. We can't
        use DRF's default ``UniqueValidator`` here because it runs before
        ``create()`` and would block the auto-suffix path. PATCH renames
        are intentionally strict — deliberate user choices deserve explicit
        feedback when they conflict.
        """
        return _validate_name_unique_on_update(
            self.instance, MissionTemplate.objects.all(), value, "mission"
        )

    def validate(self, attrs: dict) -> dict:
        """Run ``MissionTemplate._validate_invariants()`` so cross-field rules surface as DRF 400.

        DRF doesn't call ``Model.clean()`` automatically. Both this method and
        ``MissionTemplate.clean()`` delegate to ``_validate_invariants``, which
        is the single source of truth — adding a new invariant there covers both
        paths automatically (the explicit kwargs list makes a missing field a
        NameError at the call site rather than a silent bypass).
        """
        attrs = super().validate(attrs)

        def field(name: str, default: object) -> object:
            if name in attrs:
                return attrs[name]
            if self.instance is not None:
                return getattr(self.instance, name, default)
            return default

        try:
            MissionTemplate.validate_invariants(
                level_band_min=int(field("level_band_min", 0)),
                level_band_max=int(field("level_band_max", 0)),
                percent_replace=int(field("percent_replace", 0)),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs

    def validate_access_tier(self, value: str) -> str:
        """Guard the flip to OPEN: every attached giver must be publishable.

        Only enforces on UPDATE (instance exists). Create flows through
        unguarded — a brand-new template with no givers can be authored
        directly as STAFF_ONLY (the model default) and only later flipped
        to OPEN once givers are wired up.
        """
        if value != self._OPEN_TIER_VALUE:
            return value
        instance = self.instance
        if instance is None:
            return value  # create — let the model layer accept either tier
        unready: list[str] = [
            giver.name for giver in instance.givers.all() if not giver.is_publishable
        ]
        if unready:
            msg = (
                "Cannot flip to OPEN: the following attached giver(s) are "
                "not publishable (no target set): " + ", ".join(unready)
            )
            raise serializers.ValidationError(msg)
        return value

    def create(self, validated_data: dict) -> MissionTemplate:  # type: ignore[override]
        from django.db import IntegrityError, transaction  # noqa: PLC0415

        from world.missions.services.naming import next_available_name  # noqa: PLC0415

        original_name = validated_data["name"]
        validated_data["name"] = next_available_name(original_name, MissionTemplate.objects.all())
        try:
            # Wrap in a savepoint so that if the INSERT fails with
            # IntegrityError, any enclosing @transaction.atomic caller's
            # transaction is NOT poisoned ("current transaction is aborted").
            with transaction.atomic():
                return super().create(validated_data)  # type: ignore[return-value]
        except IntegrityError:
            # Concurrent create with the same name beat us between the
            # next_available_name SELECT and our INSERT. Recompute the
            # suffix (now seeing the just-committed row) and retry once.
            validated_data["name"] = next_available_name(
                original_name, MissionTemplate.objects.all()
            )
            return super().create(validated_data)  # type: ignore[return-value]


class _ActiveInstanceSerializer(serializers.Serializer):
    """One row in the template-detail footprint's ``active_instances`` list.

    Pure serialization — no model bound. Built by the detail view from
    the MissionInstance queryset; carries the bits the authoring tool
    needs at a glance (instance id, where the run sits, who's holding
    the contract). Not a ModelSerializer because the response shape is
    flattened across MissionInstance + MissionParticipant + ObjectDB.
    """

    instance_id = serializers.IntegerField()
    current_node_key = serializers.CharField(allow_null=True)
    contract_holder = serializers.CharField(allow_null=True)


class MissionTemplateDetailSerializer(MissionTemplateSerializer):
    """Detail response: list fields + §5 footprint.

    Adds:
    - ``lifetime_completions`` — count of MissionInstance rows in
      COMPLETE status for this template.
    - ``active_instances`` — list of currently-ACTIVE runs with their
      current node key + contract holder name.

    The authoring tool surfaces these so authors can see at a glance
    how their template is being consumed.
    """

    lifetime_completions = serializers.SerializerMethodField()
    active_instances = serializers.SerializerMethodField()

    class Meta(MissionTemplateSerializer.Meta):
        fields = [
            *MissionTemplateSerializer.Meta.fields,
            "lifetime_completions",
            "active_instances",
        ]

    def get_lifetime_completions(self, obj: MissionTemplate) -> int:
        return MissionInstance.objects.filter(template=obj, status=MissionStatus.COMPLETE).count()

    def get_active_instances(self, obj: MissionTemplate) -> list[dict]:
        """Flatten ACTIVE runs into the response — one row per instance.

        SharedMemoryModel identity map keeps current_node + participants
        FK-cached after the prefetch; the in-Python walk fires no extra
        queries beyond the prefetched ones.
        """
        from django.db.models import Prefetch  # noqa: PLC0415

        from world.missions.models import MissionParticipant  # noqa: PLC0415

        rows: list[dict] = []
        instances = (
            MissionInstance.objects.filter(template=obj, status=MissionStatus.ACTIVE)
            .select_related("current_node")
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=MissionParticipant.objects.select_related("character"),
                    to_attr="cached_participants",
                ),
            )
            .order_by("pk")
        )
        for instance in instances:
            current_node_key = instance.current_node.key if instance.current_node else None
            contract_holder = None
            for participant in instance.cached_participants:
                if participant.is_contract_holder:
                    contract_holder = participant.character.db_key
                    break
            rows.append(
                {
                    "instance_id": instance.pk,
                    "current_node_key": current_node_key,
                    "contract_holder": contract_holder,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# D2 editor CRUD serializers — one per nested model. ModelSerializer with
# all editable fields (plus the parent FK so create works through nested
# routes). Validation that depends on the WHOLE GRAPH (entry-node
# uniqueness, route-set completeness) lives in dedicated validate/
# actions (D2.validate) — these serializers only enforce single-row
# invariants the model's clean() already covers.
# ---------------------------------------------------------------------------


class MissionNodeSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionNode rows.

    ``allowed_riders`` exposes the consequence M2M as a list of PKs (the
    authoring UI passes them through unchanged). Editor layout fields
    (editor_x / editor_y) round-trip; flavor_text and its needs_rewrite
    sibling are both editable.
    """

    class Meta:
        model = MissionNode
        fields = [
            "id",
            "template",
            "key",
            "is_entry",
            "conflict_mode",
            "joint_combine",
            "joint_count",
            "allowed_riders",
            "deny_all_riders",
            "editor_x",
            "editor_y",
            "flavor_text",
            "flavor_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOption rows (authored or challenge-sourced).

    Both source_kind values are editable; consumer code distinguishes via
    the kind field (BRANCH vs CHECK). visibility_rule is a JSONField that
    rides through; the predicate-tree builder API (D5) is what authors
    actually use to write it.
    """

    class Meta:
        model = MissionOption
        fields = [
            "id",
            "node",
            "order",
            "option_kind",
            "source_kind",
            "visibility_rule",
            "authored_check_type",
            "authored_base_risk",
            "authored_ic_framing",
            "authored_ic_framing_needs_rewrite",
            "branch_target",
            "challenge",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOptionRoute rows (one per outcome tier per option)."""

    class Meta:
        model = MissionOptionRoute
        fields = [
            "id",
            "option",
            "outcome_tier",
            "target_node",
            "is_random_set",
            "consequence",
            "outcome_text",
            "outcome_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteCandidateSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOptionRouteCandidate (random-set rolls)."""

    class Meta:
        model = MissionOptionRouteCandidate
        fields = [
            "id",
            "route",
            "target_node",
            "weight",
            "consequence",
            "outcome_text",
            "outcome_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteRewardSerializer(serializers.ModelSerializer):
    """Editor CRUD for reward lines attached to a route OR a candidate (XOR).

    Model-level CheckConstraint + clean() both enforce exactly-one-parent.
    DRF's ModelSerializer skips clean() by default, so we mirror the XOR
    check here as ``validate()`` to surface a clean 400 instead of letting
    the DB constraint raise IntegrityError → 500.
    """

    class Meta:
        model = MissionOptionRouteReward
        fields = ["id", "route", "candidate", "kind", "sink", "amount"]
        read_only_fields = ["id"]

    # Module-level constants for the XOR validation messages — avoid
    # inline string literals in raise statements (TRY003/EM101).
    _ERR_BOTH_NULL = "Exactly one of route or candidate must be set; both are null."
    _ERR_BOTH_SET = "Cannot set both route and candidate — pick one."

    def validate(self, attrs: dict) -> dict:
        # Honor partial updates: fall back to instance values for fields
        # not in attrs (PATCH).
        instance = self.instance
        route = attrs.get("route")
        if route is None and instance is not None:
            route = instance.route
        candidate = attrs.get("candidate")
        if candidate is None and instance is not None:
            candidate = instance.candidate
        if route is None and candidate is None:
            raise serializers.ValidationError(self._ERR_BOTH_NULL)
        if route is not None and candidate is not None:
            raise serializers.ValidationError(self._ERR_BOTH_SET)
        return attrs


# ---------------------------------------------------------------------------
# D3 giver-library serializers — MissionGiver + MissionGiverOffering (the
# template-link through-model). NPCStanding (the per-(persona, npc_persona)
# row, formerly MissionGiverStanding) is serialized in
# `world.npc_services.serializers`.
# ---------------------------------------------------------------------------


class MissionGiverSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionGiver rows.

    ``target`` is a generic ObjectDB FK; the model's clean() validates
    the typeclass against ``giver_kind`` (NPC->Character, ROOM_TRIGGER->
    Room, ENVIRONMENTAL_DETAIL->non-Character/Room/Exit Object). The
    serializer passes both through; DRF's ModelSerializer doesn't call
    clean(), so we proxy it from validate() to surface 400 instead of
    IntegrityError.

    ``is_publishable`` is the authoring-UI gate (Phase B2/B7 deviation
    note) — exposed read-only here so the Studio can grey out "publish"
    when the giver lacks its target.
    """

    is_publishable = serializers.BooleanField(read_only=True)

    class Meta:
        model = MissionGiver
        fields = [
            "id",
            "name",
            "giver_kind",
            "target",
            "org",
            "is_active",
            "is_publishable",
        ]
        read_only_fields = ["id", "is_publishable"]
        # Suppress DRF's auto-generated UniqueValidator on ``name``.
        # The create() override calls next_available_name() to resolve
        # collisions via auto-suffix before the DB write, so a
        # UniqueValidator firing before create() would block that logic.
        extra_kwargs = {"name": {"validators": []}}

    # Field key used when proxying clean() errors back to the API client.
    _TARGET_FIELD = "target"

    def validate_name(self, value: str) -> str:
        """On UPDATE: reject names already taken by another giver.

        On CREATE: ``create()`` auto-suffixes via ``next_available_name``,
        so this validator is a no-op. PATCH renames are intentionally
        strict — see MissionTemplateSerializer.validate_name.
        """
        return _validate_name_unique_on_update(
            self.instance, MissionGiver.objects.all(), value, "giver"
        )

    def validate(self, attrs: dict) -> dict:
        # Build the candidate instance and run clean() so typeclass
        # validation surfaces as a 400 with the field-keyed error.
        instance = self.instance
        merged_kind = attrs.get("giver_kind") or (instance.giver_kind if instance else None)
        merged_target = (
            attrs.get(self._TARGET_FIELD)
            if self._TARGET_FIELD in attrs
            else (instance.target if instance else None)
        )
        if merged_target is not None and merged_kind is not None:
            candidate = MissionGiver(giver_kind=merged_kind, target=merged_target)
            try:
                candidate.clean()
            except DjangoValidationError as exc:
                # MissionGiver.clean() raises with a field-keyed message_dict;
                # surface those keys directly rather than stringifying the
                # exception (which would leak typeclass paths and similar).
                raise serializers.ValidationError(exc.message_dict) from exc
        return attrs

    def create(self, validated_data: dict) -> MissionGiver:  # type: ignore[override]
        from django.db import IntegrityError, transaction  # noqa: PLC0415

        from world.missions.services.naming import next_available_name  # noqa: PLC0415

        original_name = validated_data["name"]
        validated_data["name"] = next_available_name(original_name, MissionGiver.objects.all())
        try:
            # Wrap in a savepoint so that if the INSERT fails with
            # IntegrityError, any enclosing @transaction.atomic caller's
            # transaction is NOT poisoned ("current transaction is aborted").
            with transaction.atomic():
                return super().create(validated_data)  # type: ignore[return-value]
        except IntegrityError:
            # Concurrent create with the same name beat us between the
            # next_available_name SELECT and our INSERT. Recompute the
            # suffix (now seeing the just-committed row) and retry once.
            validated_data["name"] = next_available_name(original_name, MissionGiver.objects.all())
            return super().create(validated_data)  # type: ignore[return-value]


class MissionGiverOfferingSerializer(serializers.ModelSerializer):
    """Editor CRUD for the giver<->template through-model.

    ``weight_override`` and ``requirements_override`` are the two
    per-link knobs; the model's clean() rejects weight_override=0
    (silent disable trap), which proxies through validate() below.
    """

    class Meta:
        model = MissionGiverOffering
        fields = [
            "id",
            "giver",
            "template",
            "weight_override",
            "requirements_override",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        weight_override = attrs.get("weight_override")
        if weight_override == 0:
            msg = (
                "weight_override=0 would silently disable this offering at draw time. "
                "Use null (= fall back to template.base_weight) or any positive integer."
            )
            raise serializers.ValidationError({"weight_override": msg})
        return attrs


class MissionInstanceSerializer(serializers.ModelSerializer):
    """Staff-side serializer for MissionInstance (assign + remove surfaces).

    Read-only for the common fields; the staff-assign action wraps the
    `staff_assign_mission` service to populate these (so authors don't
    POST to this endpoint to create instances — assign is a deliberate
    operator gesture).
    """

    class Meta:
        model = MissionInstance
        fields = [
            "id",
            "template",
            "current_node",
            "status",
            "started_at",
            "completed_at",
            "source_beat",
        ]
        read_only_fields = ["id", "started_at"]


class MissionCategorySerializer(serializers.ModelSerializer):
    """List + detail serializer for MissionCategory browse.

    Read-only resource exposed via MissionCategoryViewSet; categories
    are seeded via fixture/admin, not authored through the API.
    """

    class Meta:
        model = MissionCategory
        fields = ["id", "name", "description", "display_order"]
        read_only_fields = ["id"]
