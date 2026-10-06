from collections import defaultdict
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from evennia.objects.models import ObjectDB
from evennia.utils.utils import compress_whitespace, iter_to_str

from commands.types import Kwargs
from flows.consts import GLANCE_MODE

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from behaviors.models import BehaviorPackageInstance
    from flows.scene_data_manager import SceneDataManager
    from typeclasses.types import ArxTypeclass
    from world.scenes.models import Scene


def select_display_name[NameT: str | None](
    base_name: NameT,
    *,
    object_id: int,
    viewer_id: int | None,
    fake_name: str | None = None,
    real_name_viewers: Collection[int] = (),
) -> str | NameT:
    """Select the existing flow-local bare name without granting permission.

    Args:
        base_name: Caller-selected base, including an explicit empty/null name.
        object_id: Identity of the presented object.
        viewer_id: Observer identity, or None when there is no observer state.
        fake_name: Truthy presentation override for observers outside the list.
        real_name_viewers: Current flow-local presentation exceptions, not durable
            protected-identity authorization.

    Returns:
        The selected name, preserving empty/null base values exactly.
    """
    if fake_name and (
        viewer_id is None or (viewer_id != object_id and viewer_id not in real_name_viewers)
    ):
        return fake_name
    return base_name


# Accept presentation values directly so callers need not construct or load state.
def project_display_name(  # noqa: PLR0913
    base_name: str | None,
    *,
    object_id: int,
    viewer_id: int | None,
    fake_name: str | None = None,
    real_name_viewers: Collection[int] = (),
    name_prefix: str = "",
    name_suffix: str = "",
    name_prefix_map: Mapping[int, str] | None = None,
    name_suffix_map: Mapping[int, str] | None = None,
) -> str:
    """Apply existing flow-local name selection and observer decorations.

    Args:
        base_name: Caller-selected base name, not an authorization result.
        object_id: Identity of the presented object.
        viewer_id: Observer identity, or None for global decorations only.
        fake_name: Optional flow-local alternate name.
        real_name_viewers: Current flow-local presentation exceptions.
        name_prefix: Global prefix.
        name_suffix: Global suffix.
        name_prefix_map: Observer overrides; an empty string overrides globally.
        name_suffix_map: Observer overrides; an empty string overrides globally.

    Returns:
        The decorated string, with the original f-string null-name semantics.
    """
    base = select_display_name(
        base_name,
        object_id=object_id,
        viewer_id=viewer_id,
        fake_name=fake_name,
        real_name_viewers=real_name_viewers,
    )
    prefix = name_prefix
    suffix = name_suffix
    if viewer_id is not None:
        if name_prefix_map is not None:
            prefix = name_prefix_map.get(viewer_id, prefix)
        if name_suffix_map is not None:
            suffix = name_suffix_map.get(viewer_id, suffix)
    return f"{prefix}{base}{suffix}"


def unwrap_objectdb(obj: "BaseState | ObjectDB") -> "ObjectDB":
    """Unwrap a BaseState wrapper to its underlying ObjectDB.

    The flow execution layer may pass a ``BaseState`` (e.g. ``CharacterState``)
    rather than a raw ``ObjectDB`` when a parameter is resolved via
    ``_resolve_service_param``. Explicit isinstance dispatch — a getattr
    default here would silently swallow genuine attribute bugs (#2386).
    """
    return obj.obj if isinstance(obj, BaseState) else obj


class BaseState:
    """Ephemeral wrapper around an Evennia object.

    A BaseState exposes attributes such as ``name`` and ``description`` that
    mirror the underlying object but can be modified during a flow run. Changes
    are kept only within the current ``SceneDataManager`` so they never touch
    the database.
    Subclasses may add additional convenience properties for specific object
    types.
    """

    def __init__(self, obj: "ArxTypeclass", context: "SceneDataManager") -> None:
        """Initialize the state.

        Args:
            obj: The Arx typeclass object to wrap.
            context: SceneDataManager this state belongs to.

        The state can present a ``fake_name`` to observers that are not in
        ``real_name_viewers``. Optional ``name_prefix`` and ``name_suffix``
        values are applied to the chosen base name. These decorations may also
        be customized per observer using ``name_prefix_map`` and
        ``name_suffix_map``.
        """
        self.obj = obj
        self.context = context
        self.fake_name: str | None = None
        self.real_name_viewers: set[int] = set()
        self.name_prefix: str = ""
        self.name_suffix: str = ""
        self.name_prefix_map: dict[int, str] = {}
        self.name_suffix_map: dict[int, str] = {}
        self.packages: list[BehaviorPackageInstance] = []
        # Generic seam: ``obj`` may be any stateable object — a typeclassed game
        # object (which carries the ``character_sheet`` property) or a plain model
        # (ItemInstance in some flows). Explicit type dispatch, not getattr-default.
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.obj.character_sheet if isinstance(self.obj, ObjectDB) else None
        if sheet is not None:
            try:
                persona = active_persona_for_sheet(sheet)
            except Persona.DoesNotExist:
                persona = None
        else:
            persona = None
        self._resolved_persona = persona
        self.thumbnail_url = resolve_thumbnail(self.obj, persona=persona)

    # ------------------------------------------------------------------
    # Attribute access helpers
    # ------------------------------------------------------------------

    def set_attribute(self, name: str, value: object) -> None:
        """Set ``name`` to ``value`` on this state."""

        setattr(self, name, value)

    def get_attribute(self, name: str, default: object = None) -> object:
        """Return attribute ``name`` or ``default`` if missing."""

        return getattr(self, name, default)

    def __str__(self) -> str:
        """Return the default display name."""
        return self.get_display_name()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BaseState):
            return self.obj == other.obj
        return self.obj == other

    def __hash__(self) -> int:
        return hash(self.obj)

    @property
    def pk(self) -> int:
        """Return the wrapped object's primary key."""
        return int(self.obj.pk)

    @property
    def account(self) -> "AccountDB | None":
        """Return the Account associated with this object, if any."""
        try:
            # Evennia dynamic property
            # noinspection PyUnresolvedReferences
            return self.obj.account
        except AttributeError:
            return None

    @property
    def active_scene(self) -> "Scene | None":
        """Return the active scene for this object, if any."""
        try:
            return self.obj.active_scene
        except AttributeError:
            return None

    @cached_property
    def gender(self) -> str:
        """Gender for funcparser pronoun helpers."""
        return self.obj.gender

    @cached_property
    def name(self) -> str:
        # Compute the default name from the Evennia object.
        return self.obj.key

    @cached_property
    def description(self) -> str:
        # Use item_data instead of .db to get the description.
        try:
            return self.obj.item_data.desc or "You see nothing of note."
        except AttributeError:
            return "You see nothing of note."

    @property
    def template(self) -> str:
        # A simple default template.
        return "{name}: {description}"

    @property
    def contents(self) -> list["BaseState | None"]:
        """
        Returns a list of contained state objects. It uses the context to convert each
        contained Evennia object (from self.obj.contents) into its corresponding state.
        """
        # Assumes self.obj.contents is a list of Evennia objects.
        return [self.context.get_state_by_pk(obj.pk) for obj in self.obj.contents]

    def get_categories(self) -> dict[str, object]:
        """
        Returns additional category data as a dictionary. Subclasses can override
        this method to supply extra template keys.
        """
        return {}

    # ------------------------------------------------------------------
    # Appearance helpers (inspired by Evennia's DefaultObject)
    # ------------------------------------------------------------------

    @property
    def appearance_template(self) -> str:
        """Template used by `return_appearance`."""
        return "{name}\n{desc}"

    # Display-component methods
    def get_display_name(
        self,
        looker: "BaseState | object | None" = None,
        **kwargs: Kwargs,
    ) -> str:
        """Return the name visible to ``looker``.

        Args:
            looker: State observing this one. If ``None``, no per-looker
                overrides apply.

        Returns:
            The display name appropriate for ``looker``.
        """
        looker_state: BaseState | None = None
        if isinstance(looker, BaseState):
            looker_state = looker
        elif looker is not None:
            try:
                pk = looker.pk
            except AttributeError:
                pk = None
            if pk is not None:
                looker_state = self.context.get_state_by_pk(pk)

        # Preserve subclass identity selection before applying shared decorations.
        return project_display_name(
            self._base_display_name(looker_state),
            object_id=self.obj.pk,
            viewer_id=looker_state.obj.pk if looker_state is not None else None,
            name_prefix=self.name_prefix,
            name_suffix=self.name_suffix,
            name_prefix_map=self.name_prefix_map,
            name_suffix_map=self.name_suffix_map,
        )

    def _base_display_name(self, looker_state: "BaseState | None") -> str:
        """The bare name ``looker_state`` sees, before prefix/suffix.

        Subclasses override to resolve identity (e.g. ``CharacterState`` renders the presented
        persona — real name / discovery reveal / anonymous sdesc — per viewer).
        """
        return select_display_name(
            self.name,
            object_id=self.obj.pk,
            viewer_id=looker_state.obj.pk if looker_state is not None else None,
            fake_name=self.fake_name,
            real_name_viewers=self.real_name_viewers,
        )

    def get_extra_display_name_info(self, **kwargs: Kwargs) -> str:
        return ""

    def get_display_desc(
        self,
        mode: str = "look",
        **kwargs: Kwargs,
    ) -> str:
        """Return the object's description unless in "glance" mode."""

        if mode == GLANCE_MODE:
            return ""
        return str(self.description)

    def _get_contents(self, content_type: str) -> list["BaseState"]:
        """Return contained states of the given type that should be displayed."""
        states = [
            self.context.get_state_by_pk(obj.pk)
            for obj in self.obj.contents_get(content_type=content_type)
        ]
        return [st for st in states if st and st.get_display_name()]

    def get_display_exits(self, **kwargs: Kwargs) -> str:
        exits = self._get_contents("exit")
        names = iter_to_str(
            (ex.get_display_name(**kwargs) for ex in exits),
            endsep=", and",
        )
        return f"|wExits:|n {names}" if names else ""

    def get_display_characters(self, **kwargs: Kwargs) -> str:
        characters = self._get_contents("character")
        looker = kwargs.get("looker")
        looker_obj: ObjectDB | None = None
        if isinstance(looker, BaseState):
            looker_obj = looker.obj
        elif isinstance(looker, ObjectDB):
            looker_obj = looker
        if looker_obj is not None:
            from world.conditions.services import can_perceive  # noqa: PLC0415

            # #1225: a concealed-and-undetected character is imperceptible to this
            # looker — omit entirely, mirroring the web room-state gate. The looker
            # always perceives themselves regardless of their own concealment.
            characters = [
                ch for ch in characters if ch.obj == looker_obj or can_perceive(looker_obj, ch.obj)
            ]
        names = iter_to_str(
            (ch.get_display_name(**kwargs) for ch in characters),
            endsep=", and",
        )
        return f"|wCharacters:|n {names}" if names else ""

    def get_display_things(self, **kwargs: Kwargs) -> str:
        things = self._get_contents("object")
        grouped = defaultdict(list)
        for thing in things:
            grouped[thing.get_display_name(**kwargs)].append(thing)
        thing_names = []
        for name, group in sorted(grouped.items()):
            count = len(group)
            obj = group[0].obj
            singular, plural = obj.get_numbered_name(count, None, key=name)
            thing_names.append(singular if count == 1 else plural)
        names = iter_to_str(thing_names, endsep=", and")
        return f"|wYou see:|n {names}" if names else ""

    def get_display_header(self, **kwargs: Kwargs) -> str:
        return ""

    def get_display_footer(self, **kwargs: Kwargs) -> str:
        return ""

    def format_appearance(
        self,
        appearance: str,
        **kwargs: Kwargs,
    ) -> str:
        return str(compress_whitespace(appearance)).strip()

    def return_appearance(self, mode: str = "look", **kwargs: Kwargs) -> str:
        appearance = self.appearance_template.format(
            name=self.get_display_name(**kwargs),
            extra_name_info=self.get_extra_display_name_info(**kwargs),
            desc=self.get_display_desc(mode=mode, **kwargs),
            header=self.get_display_header(**kwargs),
            footer=self.get_display_footer(**kwargs),
            exits=self.get_display_exits(**kwargs),
            characters=self.get_display_characters(**kwargs),
            things=self.get_display_things(**kwargs),
        )
        return self.format_appearance(appearance, **kwargs)

    def msg(  # noqa: PLR0913 - Mirrors Evennia msg signature for compatibility
        self,
        text: str | tuple[str, dict[str, object]] | None = None,
        from_obj: object | None = None,
        session: object | None = None,
        options: object | None = None,
        *,
        payload: object | None = None,
        payload_key: str = "vn_message",
        **kwargs: object,
    ) -> None:
        """Send a message to the underlying Evennia object.

        This mirrors ``DefaultObject.msg`` so that service functions can work
        transparently with states or raw objects. ``text`` may be Evennia's
        ``(text, {options})`` tuple form, which is forwarded unchanged; the
        session handler turns that dict into the outgoing frame's kwargs.
        """

        params: dict[str, object] = {}
        if from_obj is not None:
            params["from_obj"] = from_obj
        if options is not None:
            params["options"] = options
        params.update(kwargs)

        # Send text message with optional payload
        if text is not None:
            if session is not None:
                params["session"] = session
            if payload is not None:
                # Send both text and payload in one call
                params[payload_key] = ((), payload)
            self.obj.msg(text, **params)
        elif payload is not None:
            # Send only payload if no text
            self.obj.msg(**{payload_key: ((), payload)})

    # ------------------------------------------------------------------
    # Package hooks
    # ------------------------------------------------------------------

    def _run_package_hook(self, hook_name: str, *args: object, **kwargs: Kwargs) -> object | None:
        """Run ``hook_name`` on attached behavior packages."""

        for pkg in self.packages:
            func = pkg.get_hook(hook_name)
            if func is None:
                continue
            result = func(self, pkg, *args, **kwargs)
            if result is not None:
                return result
        return None

    def initialize_state(self) -> None:
        """Call the ``initialize_state`` hook on attached packages."""

        self._run_package_hook("initialize_state")

    def apply_attribute_modifiers(self, attr_name: str, value: object) -> object:
        """Return ``value`` modified by any packages."""

        modified = value
        for pkg in self.packages:
            func = pkg.get_hook(f"modify_{attr_name}")
            if func is None:
                continue
            modified = func(self, pkg, modified)
        return modified

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return True if ``actor`` may move this object to ``dest``.

        Args:
            actor: State attempting the move.
            dest: Destination container state.

        Returns:
            bool: ``True`` if the move is allowed.

        Notes:
            Moving an object into itself is always disallowed.
        """

        if dest is self:
            return False
        result = self._run_package_hook("can_move", actor, dest)
        if result is not None:
            return bool(result)
        return True

    def can_traverse(self, actor: "BaseState | None" = None) -> bool:
        """Return True if ``actor`` may traverse this object.

        Args:
            actor: State attempting the traversal.

        Returns:
            bool: ``False`` by default, overridden in ExitState.
        """
        result = self._run_package_hook("can_traverse", actor)
        if result is not None:
            return bool(result)
        return False
