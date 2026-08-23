import re as _re
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from world.scenes.constants import InteractionMode, PoseKind
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionReaction,
    Persona,
    ReactionEmoji,
    Scene,
)
from world.scenes.place_models import InteractionReceiver
from world.scenes.types import PersonaPayload, ReactionAggregation

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerData
    from world.species.models import Language

_MAX_POSE_LENGTH = 10_000

_DANGEROUS_LINK_RE = _re.compile(
    r"\[[^\]]*\]\((?!https?://)",
    _re.IGNORECASE,
)


class InlineActionInteractionSerializer(serializers.ModelSerializer):
    """Minimal serializer for an ACTION-mode Interaction embedded in an action-link chip."""

    class Meta:
        model = Interaction
        fields = ["id", "content", "mode", "timestamp"]


class InteractionActionLinkSerializer(serializers.ModelSerializer):
    """Serializes the InteractionAction bridge for the action_links field on a POSE."""

    action_interaction = InlineActionInteractionSerializer(read_only=True)
    has_critical_effect = serializers.SerializerMethodField()

    class Meta:
        model = InteractionAction
        fields = ["id", "ordering", "action_interaction", "has_critical_effect"]

    def get_has_critical_effect(self, obj: InteractionAction) -> bool:
        """Cheap critical signal for first-paint auto-expand (#996).

        ``True`` when this action's linked ``CombatRoundAction`` targeted an
        opponent that is now ``DEFEATED`` — the dominant load-bearing outcome the
        detail panel highlights. Reads ONLY prefetched data (the linked action's
        ``cached_round_actions`` + ``focused_opponent_target``); no condition or
        vitals queries, so it stays N+1-safe. The prefetch is set up in
        ``interaction_views`` as
        ``action_links__action_interaction__combat_round_actions`` with
        ``to_attr="cached_round_actions"`` and ``focused_opponent_target``
        select_related, so reading ``cached_round_actions`` never queries.
        """
        from world.combat.constants import OpponentStatus  # noqa: PLC0415

        action_interaction = obj.action_interaction
        if action_interaction is None:
            return False
        # cached_round_actions is a Prefetch(to_attr=...) attribute set by the
        # interaction_views queryset; getattr with a default keeps serialization
        # safe if this serializer is ever used without that prefetch.
        # Suppression justified: mutable social prefetch on identity-mapped row; property+setter
        # pattern (see Interaction.cached_receivers) is the sanctioned conversion.
        round_actions = getattr(action_interaction, "cached_round_actions", [])  # noqa: GETATTR_LITERAL
        for round_action in round_actions:
            opponent = round_action.focused_opponent_target
            if opponent is not None and opponent.status == OpponentStatus.DEFEATED:
                return True
        return False


class InteractionReceiverSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)
    persona_id = serializers.IntegerField(source="persona.id", read_only=True)

    class Meta:
        model = InteractionReceiver
        fields = ["id", "persona_name", "persona_id"]


class InteractionListSerializer(serializers.ModelSerializer):
    persona = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    reaction_windows = serializers.SerializerMethodField()
    receiver_persona_ids = serializers.SerializerMethodField()
    place_name = serializers.SerializerMethodField()
    target_persona_ids = serializers.SerializerMethodField()
    action_links = InteractionActionLinkSerializer(
        many=True,
        read_only=True,
        source="cached_action_links",
    )
    dramatic_moment_tags = serializers.SerializerMethodField()
    dramatic_moment_suggestions = serializers.SerializerMethodField()
    endorsee_sheet_id = serializers.IntegerField(
        source="persona.character_sheet_id", read_only=True
    )
    endorsable_resonances = serializers.SerializerMethodField()
    pose_endorsers = serializers.SerializerMethodField()
    my_pose_endorsement = serializers.SerializerMethodField()
    entry_endorsers = serializers.SerializerMethodField()
    entry_endorsed_by_me = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    language_id = serializers.IntegerField(read_only=True, allow_null=True)
    language_name = serializers.SerializerMethodField()
    attributed_companion = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "persona",
            "scene",
            "place",
            "content",
            "mode",
            "visibility",
            "timestamp",
            "pose_kind",
            "is_muted",
            "language_id",
            "language_name",
            "attributed_companion",
            "endorsee_sheet_id",
            "is_favorited",
            "reactions",
            "reaction_windows",
            "receiver_persona_ids",
            "place_name",
            "target_persona_ids",
            "action_links",
            "dramatic_moment_tags",
            "dramatic_moment_suggestions",
            "endorsable_resonances",
            "pose_endorsers",
            "my_pose_endorsement",
            "entry_endorsers",
            "entry_endorsed_by_me",
        ]

    def get_persona(self, obj: Interaction) -> PersonaPayload:
        # Per-viewer name resolution (#1109): own faces and named-public faces render real;
        # discovered anonymous faces reveal "<mask> (<real>)"; undiscovered anonymous faces
        # render a composed sdesc. Resolved once for the whole page (see _persona_display_map).
        name, _is_discovered = self._persona_display_map().get(
            obj.persona_id, (obj.persona.name, False)
        )
        return PersonaPayload(
            id=obj.persona_id,
            name=name,
            thumbnail_url=obj.persona.thumbnail_url or "",
        )

    def _persona_display_map(self) -> dict[int, tuple[str, bool]]:
        """Cache the page's persona-display resolution on the shared context (O(1) queries)."""
        cached = self.context.get("_persona_display_map")
        if cached is not None:
            return cached
        from world.scenes.persona_display import build_persona_display_map  # noqa: PLC0415

        if self.parent is not None:
            rows = list(self.parent.instance or [])
        elif self.instance is not None:
            rows = [self.instance]
        else:
            rows = []
        display_map = build_persona_display_map(
            [row.persona for row in rows],
            viewer_persona_ids=set(self.context.get("persona_ids", set())),
            viewer_sheet_ids=set(self.context.get("viewer_sheet_ids", set())),
            is_staff=bool(self.context.get("is_staff", False)),
        )
        self.context["_persona_display_map"] = display_map
        return display_map

    def get_receiver_persona_ids(self, obj: Interaction) -> list[int]:
        return [r.persona_id for r in obj.cached_receivers]

    def get_place_name(self, obj: Interaction) -> str | None:
        return obj.place.name if obj.place_id else None

    def get_target_persona_ids(self, obj: Interaction) -> list[int]:
        return [p.pk for p in obj.cached_target_personas]

    def _muted_persona_ids(self) -> set[int]:
        """Lazily compute muted persona IDs, cached on the serializer context (#2087)."""
        cache_key = "_muted_persona_ids_cache"
        if cache_key not in self.context:
            from world.scenes.mute_services import muted_persona_ids_for_viewer  # noqa: PLC0415

            request = self.context.get("request")
            user = request.user if request is not None else None
            if user and user.is_authenticated:
                self.context[cache_key] = muted_persona_ids_for_viewer(viewer_account=user)
            else:
                self.context[cache_key] = set()
        return self.context[cache_key]

    def get_is_muted(self, obj: Interaction) -> bool:
        """True when this interaction's persona is muted by the viewer (#2087).

        Muted interactions stay in the feed with content blanked — the action
        still shows, just without the text. The frontend renders a "N hidden"
        divider for consecutive muted rows.
        """
        return obj.persona_id in self._muted_persona_ids()

    def get_content(self, obj: Interaction) -> str:
        """The interaction's content, blanked when the persona is muted (#2087).

        Muted personas' interactions stay visible (so the scene stays coherent)
        but their text is redacted. The viewer can click-to-expand to fetch the
        full content via the detail endpoint.
        """
        if obj.persona_id in self._muted_persona_ids():
            return ""
        return self._comprehended_content(obj)

    def _comprehended_content(self, obj: Interaction) -> str:
        """Per-viewer language comprehension (#2993). Ground truth for the
        writer's own sheets, staff, and a viewer who was a direct receiver of
        this interaction (whisper target / mutter receiver / escalated
        visibility) -- the speaker chose that audience, so it never garbles on
        reread, mirroring ``push_interaction``'s ``receiver_scoped`` live rule
        (#2993 I1). Everyone else reads through their best fluency across ONLY
        the sheets that actually participated in this interaction's SCENE
        (#2993 C1) -- ``SceneParticipation`` (world/scenes/models.py) is
        account-scoped, not persona-scoped, so it can't discriminate between
        two concurrently-active characters on the same account (the exact
        cross-character leak C1 flags); presence is instead derived from
        writer/receiver authorship within the scene itself, via
        ``_scene_participant_sheet_id_map``. An interaction with no scene
        (ephemeral broadcast, pre-#2993 row) has no participant evidence to
        check, so a non-writer/non-receiver always garbles. Deterministic
        seed - matches what the room heard live.
        """
        if obj.language_id is None:
            return obj.content
        if bool(self.context.get("is_staff", False)):
            return obj.content
        viewer_sheet_ids: set[int] = set(self.context.get("viewer_sheet_ids", set()))
        if obj.persona.character_sheet_id in viewer_sheet_ids:
            return obj.content
        viewer_persona_ids: set[int] = set(self.context.get("persona_ids", set()))
        receiver_persona_ids = {r.persona_id for r in obj.cached_receivers}
        if viewer_persona_ids & receiver_persona_ids:
            return obj.content
        language = obj.language
        if language.is_universal:
            return obj.content
        from world.species.language_constants import fluency_band  # noqa: PLC0415
        from world.species.language_services import render_speech  # noqa: PLC0415

        speaker_band = fluency_band(
            self._fluency_for_sheet(obj.persona.character_sheet_id, language)
        )
        if obj.scene_id is None:
            participant_sheet_ids: set[int] = set()
        else:
            participant_sheet_ids = self._scene_participant_sheet_id_map().get(obj.scene_id, set())
        listener_value = max(
            (self._fluency_for_sheet(sid, language) for sid in participant_sheet_ids),
            default=0,
        )
        return render_speech(
            obj.content,
            language=language,
            speaker_band=speaker_band,
            listener_value=listener_value,
        )

    def _scene_participant_sheet_id_map(self) -> dict[int, set[int]]:
        """Context-cached scene_id -> set of viewer sheet_ids that PARTICIPATED
        in that scene (#2993 C1), for the language-comprehension gate.

        "Participated" means the sheet's Persona wrote or received at least one
        Interaction within that scene -- the precise per-character signal
        ``SceneParticipation`` can't provide (it's account-scoped). Batched
        page-wide in two queries total (writer authorship + receiver rows across
        every scene on the page), never one query per row.
        """
        cache_key = "_scene_participant_sheet_ids_cache"
        if cache_key in self.context:
            return self.context[cache_key]

        if self.parent is not None:
            rows = list(self.parent.instance or [])
        elif self.instance is not None:
            rows = [self.instance]
        else:
            rows = []
        scene_ids = {row.scene_id for row in rows if row.scene_id is not None}
        viewer_sheet_ids: set[int] = set(self.context.get("viewer_sheet_ids", set()))

        result: dict[int, set[int]] = {}
        if scene_ids and viewer_sheet_ids:
            writer_rows = Interaction.objects.filter(
                scene_id__in=scene_ids,
                persona__character_sheet_id__in=viewer_sheet_ids,
            ).values_list("scene_id", "persona__character_sheet_id")
            for scene_id, sheet_id in writer_rows:
                result.setdefault(scene_id, set()).add(sheet_id)

            receiver_rows = InteractionReceiver.objects.filter(
                interaction__scene_id__in=scene_ids,
                persona__character_sheet_id__in=viewer_sheet_ids,
            ).values_list("interaction__scene_id", "persona__character_sheet_id")
            for scene_id, sheet_id in receiver_rows:
                result.setdefault(scene_id, set()).add(sheet_id)

        self.context[cache_key] = result
        return result

    def _fluency_map(self, language: "Language") -> dict[int, int]:
        """Context-cached sheet_id -> fluency value for one language (#2993).

        One query per (page, language): covers every writer sheet on the page
        plus the viewer's own sheets, so ``_fluency_for_sheet`` never queries
        per-row. Cached on the shared context, mirroring ``_muted_persona_ids``.
        """
        cache: dict[int, dict[int, int]] = self.context.setdefault("_fluency_map_cache", {})
        if language.pk in cache:
            return cache[language.pk]
        if language.trait_id is None:
            cache[language.pk] = {}
            return cache[language.pk]

        from world.traits.models import CharacterTraitValue  # noqa: PLC0415

        if self.parent is not None:
            rows = list(self.parent.instance or [])
        elif self.instance is not None:
            rows = [self.instance]
        else:
            rows = []
        writer_sheet_ids = {row.persona.character_sheet_id for row in rows}
        viewer_sheet_ids: set[int] = set(self.context.get("viewer_sheet_ids", set()))
        sheet_ids = writer_sheet_ids | viewer_sheet_ids
        fluency_map: dict[int, int] = dict(
            CharacterTraitValue.objects.filter(
                trait_id=language.trait_id, character_id__in=sheet_ids
            ).values_list("character_id", "value")
        )
        cache[language.pk] = fluency_map
        return fluency_map

    def _fluency_for_sheet(self, sheet_id: int | None, language: "Language") -> int:
        if sheet_id is None:
            return 0
        return self._fluency_map(language).get(sheet_id, 0)

    def get_language_name(self, obj: Interaction) -> str | None:
        return obj.language.name if obj.language_id else None

    def get_attributed_companion(self, obj: Interaction) -> dict | None:
        """Cosmetic companion pose attribution (#3294): ``{id, name}`` or ``None``.

        Authorship stays entirely on ``persona`` — already resolved above with the
        full per-viewer display/mask/discovery treatment via ``_persona_display_map``.
        The frontend builds the owner tell ("via <owner>") from that same resolved
        ``persona`` field rather than a second identity-resolution path here, so a
        masked owner's companion pose correctly shows the mask, never the real name.
        """
        if obj.attributed_companion_id is None:
            return None
        return {"id": obj.attributed_companion_id, "name": obj.attributed_companion.name}

    def get_is_favorited(self, obj: Interaction) -> bool:
        roster_entry_ids: set[int] = self.context.get("roster_entry_ids", set())
        if not roster_entry_ids:
            return False
        return any(f.roster_entry_id in roster_entry_ids for f in obj.cached_favorites)

    def _account_player_for_persona(self, persona: Persona | None) -> "PlayerData | None":
        """Resolve + memoize a persona's current player (#2996), cached per request.

        Mirrors ``world.scenes.block_services._persona_player``'s walk. Memoized on the
        serializer context (keyed by persona id) so a reactor who appears on several poses
        in one page is only resolved once.
        """
        if persona is None:
            return None
        cache = self.context.setdefault("_account_player_cache", {})
        if persona.pk in cache:
            return cache[persona.pk]

        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        player = None
        try:
            roster_entry = persona.character_sheet.roster_entry
        except ObjectDoesNotExist:
            roster_entry = None
        if roster_entry is not None:
            current = roster_entry.current_tenure
            player = current.player_data if current is not None else None
        cache[persona.pk] = player
        return player

    def _viewer_player(self) -> "PlayerData | None":
        """The requesting account's PlayerData, or None (#2996)."""
        request = self.context.get("request")
        user = request.user if request is not None else None
        if user is None or not user.is_authenticated:
            return None
        try:
            return user.player_data
        except AttributeError:
            return None

    def _visible_reaction_rows(self, rows: list, *, target_persona: Persona | None) -> list:
        """Drop reactor rows the viewer's block/mute hides (#2996 Decision 2).

        Write path (``react_to_window``/``react_to_interaction``) is unmodified — a reactor's
        own create response is always the normal success. This is the read-side filter only:
        - **block**: symmetric, but only suppresses a reactor when the VIEWER is the pose's own
          author (the "target" of the reaction) — anyone else's read is unaffected.
        - **mute**: one-way, applies to every viewer's own read regardless of whose pose it is.
        """
        viewer_player = self._viewer_player()
        if viewer_player is None:
            return rows

        from world.scenes.block_services import account_block_active  # noqa: PLC0415
        from world.scenes.mute_services import account_muted  # noqa: PLC0415

        target_player = self._account_player_for_persona(target_persona)
        viewer_is_target = target_player is not None and viewer_player.pk == target_player.pk

        visible = []
        for row in rows:
            reactor_player = self._account_player_for_persona(row.reactor_persona)
            if reactor_player is None:
                visible.append(row)
                continue
            if viewer_is_target and account_block_active(
                player_a=viewer_player, player_b=reactor_player
            ):
                continue
            if account_muted(viewer_player=viewer_player, target_player=reactor_player):
                continue
            visible.append(row)
        return visible

    def get_reaction_windows(self, obj: Interaction) -> list[dict]:
        """Reaction windows on this event (#904): choices, reactions, my_reaction.

        ``my_reaction`` is per-viewer and flows through serializer context
        (``persona_ids``) — never a Prefetch(to_attr) on the shared instance.
        """
        from world.scenes.reaction_services import get_reaction_kind  # noqa: PLC0415

        windows = getattr(obj, "cached_reaction_windows", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if windows is None:
            windows = list(obj.reaction_windows.all())
        if not windows:
            return []

        viewer_persona_ids: set[int] = self.context.get("persona_ids", set())
        payloads: list[dict] = []
        for window in windows:
            rows = getattr(window, "cached_reaction_rows", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
            if rows is None:
                rows = list(window.reactions.select_related("reactor_persona"))
            try:
                config = get_reaction_kind(window.kind)
            except DjangoValidationError:
                continue  # consumer app gone; render nothing rather than 500
            my_reaction = next(
                (r.choice for r in rows if r.reactor_persona_id in viewer_persona_ids),
                None,
            )
            rows = self._visible_reaction_rows(rows, target_persona=obj.persona)
            if config.public:
                reactions = [
                    {
                        "persona_id": r.reactor_persona_id,
                        "persona_name": r.reactor_persona.name,
                        "choice": r.choice,
                    }
                    for r in rows
                ]
            else:
                reactions = []
            counts: dict[str, int] = {}
            for r in rows:
                counts[r.choice] = counts.get(r.choice, 0) + 1
            payloads.append(
                {
                    "id": window.pk,
                    "kind": window.kind,
                    "is_open": window.is_open,
                    "public": config.public,
                    "choices": [
                        {"slug": c.slug, "label": c.label} for c in config.choices_for(window)
                    ],
                    "reactions": reactions,
                    "counts": counts,
                    "my_reaction": my_reaction,
                }
            )
        return payloads

    def get_reactions(self, obj: Interaction) -> list[ReactionAggregation]:
        """Aggregate emoji counts with reacted-by-current-user flag."""
        reaction_list = obj.cached_reactions

        counts: dict[str, int] = {}
        user_reacted: set[str] = set()
        request = self.context.get("request")
        user_id = request.user.pk if request and request.user.is_authenticated else None

        for reaction in reaction_list:
            emoji = reaction.emoji
            counts[emoji] = counts.get(emoji, 0) + 1
            if reaction.account_id == user_id:
                user_reacted.add(emoji)

        return [
            ReactionAggregation(emoji=emoji, count=count, reacted=emoji in user_reacted)
            for emoji, count in counts.items()
        ]

    def get_dramatic_moment_tags(self, obj: Interaction) -> list[dict]:
        tags = getattr(obj, "cached_dramatic_moment_tags", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if tags is None:
            return []
        return [
            {"moment_type_label": t.moment_type.label, "character_sheet_id": t.character_sheet_id}
            for t in tags
        ]

    def _viewer_can_gm_scene(self, scene: Scene | None) -> bool:
        """Mirror ``SceneListSerializer.get_viewer_can_gm`` for this interaction's scene (#2183).

        Cached on the serializer context per scene id (a page of interactions can, in
        principle, span more than one scene). For the common ``?scene=<id>`` list request,
        ``InteractionViewSet.get_serializer_context`` pre-seeds this cache with the one
        relevant scene's answer computed via a single targeted ``SceneParticipation``
        query — so this field never falls through to ``scene.is_gm()``/``scene.is_owner()``
        (which would cost a fresh ``participations_cached`` query per distinct in-memory
        Scene instance, since ``select_related`` builds a new one per row). The fallback
        below only fires for requests without a scene filter.
        """
        if scene is None:
            return False
        cache: dict[int, bool] = self.context.setdefault("_viewer_can_gm_cache", {})
        if scene.pk in cache:
            return cache[scene.pk]
        request = self.context.get("request")
        user = request.user if request is not None else None
        result = bool(
            user is not None
            and user.is_authenticated
            and (user.is_staff or scene.is_gm(user) or scene.is_owner(user))
        )
        cache[scene.pk] = result
        return result

    def get_dramatic_moment_suggestions(self, obj: Interaction) -> list[dict]:
        """PENDING dramatic-moment suggestions anchored to this interaction (#2183).

        GM-gated: a plain participant sees an empty list. Reads
        ``cached_dramatic_moment_suggestions`` (Prefetch(to_attr=...) set by the view
        queryset, already filtered to PENDING) — never a fresh query.
        """
        if not self._viewer_can_gm_scene(obj.scene):
            return []
        suggestions = getattr(obj, "cached_dramatic_moment_suggestions", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if suggestions is None:
            return []
        return [
            {
                "id": s.pk,
                "moment_type_id": s.moment_type_id,
                "moment_type_label": s.moment_type.label,
                "character_sheet_id": s.character_sheet_id,
                "success_level": s.success_level,
                "status": s.status,
            }
            for s in suggestions
        ]

    def get_endorsable_resonances(self, obj: Interaction) -> list[dict]:
        """List of resonances claimed by the endorsee (pose author).

        Reads from the prefetched ``persona__character_sheet__resonances``
        path (set up in ``interaction_views.get_queryset``) via the
        ``cached_resonances`` to_attr. Falls back to a live query if the attr
        is absent (e.g. serializer used outside the view's queryset pipeline).
        """
        sheet = obj.persona.character_sheet
        if sheet is None:
            return []
        # Suppression justified: mutable social prefetch on identity-mapped row; property+setter
        # pattern (see Interaction.cached_receivers) is the sanctioned conversion.
        resonances = getattr(sheet, "cached_resonances", None)  # noqa: GETATTR_LITERAL
        if resonances is None:
            resonances = list(sheet.resonances.select_related("resonance"))
        return [{"id": cr.resonance_id, "name": cr.resonance.name} for cr in resonances]

    def get_pose_endorsers(self, obj: Interaction) -> list[dict]:
        """List of peers who endorsed this pose, with persona info.

        Reads ``obj.cached_endorsements`` (Prefetch(to_attr=...) set by the
        view queryset). Each endorser's primary persona is pre-loaded via
        ``cached_primary_persona`` (another nested Prefetch).
        """
        out = []
        # Suppression justified: mutable social prefetch on identity-mapped row; property+setter
        # pattern (see Interaction.cached_receivers) is the sanctioned conversion.
        for e in getattr(obj, "cached_endorsements", []):  # noqa: GETATTR_LITERAL
            persona = next(iter(e.endorser_sheet.cached_primary_persona), None)
            if persona is None:
                continue
            out.append(
                {
                    "persona_id": persona.pk,
                    "persona_name": persona.name,
                    "thumbnail_url": persona.thumbnail_url or "",
                    "resonance_id": e.resonance_id,
                }
            )
        return out

    def get_my_pose_endorsement(self, obj: Interaction) -> dict | None:
        """Return the viewer's own endorsement for this pose, or None.

        Checks ``character_sheet_ids`` from context (viewer's sheet PKs) against
        each cached endorsement's ``endorser_sheet_id``.
        """
        sheet_ids: set[int] = self.context.get("character_sheet_ids", set())
        # Suppression justified: mutable social prefetch on identity-mapped row; property+setter
        # pattern (see Interaction.cached_receivers) is the sanctioned conversion.
        for e in getattr(obj, "cached_endorsements", []):  # noqa: GETATTR_LITERAL
            if e.endorser_sheet_id in sheet_ids:
                return {
                    "id": e.pk,
                    "resonance_id": e.resonance_id,
                    "settled": e.settled_at is not None,
                }
        return None

    def _entry_rows(self, obj: Interaction) -> list:
        """Return scene-entry endorsement rows for ENTRY poses only."""
        if obj.pose_kind != PoseKind.ENTRY:
            return []
        sheet_id = obj.persona.character_sheet_id
        return self.context.get("scene_entry_endorsements", {}).get(sheet_id, [])

    def get_entry_endorsers(self, obj: Interaction) -> list[dict]:
        """List of peers who gave this character a scene-entry endorsement.

        Only non-empty for ENTRY poses. Reads ``scene_entry_endorsements`` from
        context (populated by the view's ``get_serializer_context``).
        """
        out = []
        for r in self._entry_rows(obj):
            persona = next(iter(r.endorser_sheet.cached_primary_persona), None)
            if persona is None:
                continue
            out.append(
                {
                    "persona_id": persona.pk,
                    "persona_name": persona.name,
                    "thumbnail_url": persona.thumbnail_url or "",
                    "resonance_id": r.resonance_id,
                }
            )
        return out

    def get_entry_endorsed_by_me(self, obj: Interaction) -> bool:
        """True when the viewer has given this character a scene-entry endorsement."""
        sheet_ids: set[int] = self.context.get("character_sheet_ids", set())
        return any(r.endorser_sheet_id in sheet_ids for r in self._entry_rows(obj))


class InteractionDetailSerializer(InteractionListSerializer):
    receivers = InteractionReceiverSerializer(
        many=True,
        read_only=True,
        source="cached_receivers",
    )

    class Meta(InteractionListSerializer.Meta):
        fields = [
            *InteractionListSerializer.Meta.fields,
            "receivers",
        ]

    def get_content(self, obj: Interaction) -> str:
        """Detail endpoint always returns full content (#2087 — opt-in backfill).

        The list endpoint blanks content for muted personas; the detail endpoint
        is the reveal path — a viewer who clicks 'expand' fetches the full content
        here. Still subject to per-viewer language comprehension (#2993) — the
        mute reveal is not a comprehension bypass.
        """
        return self._comprehended_content(obj)


class InteractionFavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionFavorite
        fields = ["id", "interaction", "created_at"]
        read_only_fields = ["created_at"]


class InteractionReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionReaction
        fields = ["id", "interaction", "emoji", "created_at"]
        read_only_fields = ["created_at"]


class ReactionEmojiSerializer(serializers.ModelSerializer):
    """Read serializer for the active reaction-emoji catalog (#1699)."""

    class Meta:
        model = ReactionEmoji
        fields = ["emoji", "valence", "sort_order"]


class PoseSubmitSerializer(serializers.Serializer):
    """Write serializer for submitting a POSE-mode Interaction from the web frontend.

    Validates persona ownership and action_link_ids integrity before the view
    creates the Interaction and wires the auto-link service.
    """

    persona_id = serializers.IntegerField(
        help_text="PK of the Persona the requesting user is posing as.",
    )
    scene_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="PK of the Scene this pose belongs to. Null for scene-less poses.",
    )
    content = serializers.CharField(
        help_text="The written text of the pose.",
    )
    action_link_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text=(
            "Optional explicit action-link override. When provided, auto-link "
            "is skipped and InteractionAction bridges are created for exactly "
            "these ACTION Interaction ids in order. An empty list explicitly "
            "requests no links (caller opted out of auto-link this pose)."
        ),
    )

    pose_kind = serializers.ChoiceField(
        choices=PoseKind.choices,
        required=False,
        default=PoseKind.STANDARD,
        help_text=(
            "Classifies the pose (Spec C). ENTRY opens a Make-an-Entrance "
            "reaction window (#904) when the pose belongs to a scene."
        ),
    )

    target_names = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text=(
            "Optional composer-mode @Name targets (#2156). Resolved against the "
            "writer's room with the same case-insensitive exact-match semantics as "
            "the WS/telnet '@Name' prefix parser — an unresolvable name is silently "
            "skipped, not an error."
        ),
    )

    def validate_persona_id(self, value: int) -> int:
        """Confirm the persona exists and belongs to the requesting user."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context unavailable."
            raise serializers.ValidationError(msg)
        try:
            persona = Persona.objects.get(pk=value)
        except Persona.DoesNotExist:
            msg = "Persona not found."
            raise serializers.ValidationError(msg) from None

        owned_persona_ids = get_account_personas(request)
        if persona.pk not in owned_persona_ids:
            msg = "You do not own this persona."
            raise serializers.ValidationError(msg)

        return value

    def validate_scene_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if not Scene.objects.filter(pk=value).exists():
            msg = "Scene not found."
            raise serializers.ValidationError(msg)
        return value

    def validate_content(self, value: str) -> str:
        if not value.strip():
            msg = "Pose content cannot be blank."
            raise serializers.ValidationError(msg)
        if len(value) > _MAX_POSE_LENGTH:
            msg = f"Pose content exceeds the maximum length of {_MAX_POSE_LENGTH} characters."
            raise serializers.ValidationError(msg)
        if "\x00" in value:
            msg = "Pose content contains invalid characters."
            raise serializers.ValidationError(msg)
        if _DANGEROUS_LINK_RE.search(value):
            msg = "Links must use http:// or https:// URLs."
            raise serializers.ValidationError(msg)
        return value

    def validate_action_link_ids(self, value: list[int]) -> list[int]:
        """Confirm all supplied IDs reference ACTION-mode Interactions."""
        if not value:
            return value
        valid_pks = set(
            Interaction.objects.filter(
                pk__in=value,
                mode=InteractionMode.ACTION,
            ).values_list("pk", flat=True)
        )
        invalid = set(value) - valid_pks
        if invalid:
            msg = f"These IDs are not valid ACTION-mode Interactions: {sorted(invalid)}"
            raise serializers.ValidationError(msg)
        return value

    def validate(self, attrs: dict) -> dict:
        """Cross-field: persona must own the action_link_ids (same character);

        persona's character must be co-located with a located scene (#2156).
        """
        self._validate_action_link_ownership(attrs)
        self._validate_actor_co_located(attrs)
        return attrs

    def _validate_action_link_ownership(self, attrs: dict) -> None:
        """All action_link_ids must belong to the same persona as this pose."""
        action_link_ids = attrs.get("action_link_ids")
        persona_id = attrs.get("persona_id")
        if not action_link_ids or persona_id is None:
            return
        try:
            persona = Persona.objects.get(pk=persona_id)
        except Persona.DoesNotExist:
            return  # surfaced by validate_persona_id
        wrong_persona = Interaction.objects.filter(pk__in=action_link_ids).exclude(persona=persona)
        if wrong_persona.exists():
            raise serializers.ValidationError(
                {
                    "action_link_ids": (
                        "All action_link_ids must belong to the same persona as the pose."
                    )
                }
            )

    def _validate_actor_co_located(self, attrs: dict) -> None:
        """Persona's character must be co-located with a located scene (#2156)."""
        scene_id = attrs.get("scene_id")
        persona_id = attrs.get("persona_id")
        if scene_id is None or persona_id is None:
            return
        # Field validators (validate_scene_id / validate_persona_id) already guarantee
        # these rows exist by the time cross-field validation runs.
        scene = Scene.objects.get(pk=scene_id)
        persona = Persona.objects.get(pk=persona_id)
        if scene.location is None:
            return
        actor_room = persona.character_sheet.character.location
        if actor_room is None or actor_room.pk != scene.location.pk:
            raise serializers.ValidationError(
                {"scene_id": "Your character is not present in this scene's room."}
            )
