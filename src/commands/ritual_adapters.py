"""Per-ritual draft/join adapter registry.

Translates flat ``key=value`` tokens (parsed generically by ``CmdRitual._handle_draft``
/ ``_handle_join``) into the typed ``DraftParse``/``JoinParse`` structures that the
session services expect. Adapters are keyed on the ritual's ``service_function_path``.

The base ``RitualDraftAdapter`` returns empty parses — non-adapted rituals draft and
join with no extra kwargs or references, exactly as the generic path did before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from commands.exceptions import CommandError
from world.magic.types.sessions import RitualSessionReferenceSpec

if TYPE_CHECKING:
    from world.magic.models.rituals import Ritual


# ---------------------------------------------------------------------------
# Parse result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DraftParse:
    """Parsed draft tokens ready for ``draft_session(...)``."""

    session_kwargs: dict[str, Any] = field(default_factory=dict)
    session_references: list[RitualSessionReferenceSpec] = field(default_factory=list)
    initiator_participant_kwargs: dict[str, Any] = field(default_factory=dict)
    initiator_references: list[RitualSessionReferenceSpec] = field(default_factory=list)


@dataclass
class JoinParse:
    """Parsed join tokens ready for ``accept_session(...)``."""

    participant_kwargs: dict[str, Any] = field(default_factory=dict)
    references: list[RitualSessionReferenceSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Adapter base class
# ---------------------------------------------------------------------------


class RitualDraftAdapter:
    """Base adapter — returns empty parses for unregistered rituals.

    Non-adapted rituals draft and join with no extra kwargs or references.
    """

    def parse_draft(self, *, kwargs: dict[str, str], caller: Any) -> DraftParse:
        """Translate flat kwargs into a ``DraftParse``. Default: empty."""
        return DraftParse()

    def parse_join(self, *, kwargs: dict[str, str], caller: Any) -> JoinParse:
        """Translate flat kwargs into a ``JoinParse``. Default: empty."""
        return JoinParse()


# ---------------------------------------------------------------------------
# Soul-tether adapter
# ---------------------------------------------------------------------------

_SOUL_TETHER_SERVICE_PATH = "world.magic.services.soul_tether.accept_soul_tether_via_session"
_PARTICIPANT_ROLE_KEY = "soul_tether_role"
_SESSION_RESONANCE_ID_KEY = "resonance_id"
_SESSION_WRITEUP_KEY = "writeup"


def _resolve_soul_tether_role(token: str) -> str:
    """Map a telnet ``role=`` token to a SoulTetherRole value.

    Returns the canonical uppercase enum value (``"SINNER"`` / ``"SINEATER"``)
    that the fire handler ``accept_soul_tether_via_session`` compares against.
    Raises ``CommandError`` for unknown roles.
    """
    from world.magic.types.soul_tether import SoulTetherRole  # noqa: PLC0415

    normalized = token.strip().upper()
    for role in SoulTetherRole:
        if normalized == role.value:
            return role.value
    msg = f"Unknown role '{token}'. Use role=sinner or role=sineater."
    raise CommandError(msg)


class SoulTetherAdapter(RitualDraftAdapter):
    """Adapter for the soul-tether BILATERAL session ritual.

    Translates ``role=``, ``resonance=``, and ``writeup=`` tokens into the
    ``draft_session`` kwargs that ``accept_soul_tether_via_session`` expects.
    """

    def parse_draft(self, *, kwargs: dict[str, str], caller: Any) -> DraftParse:
        """Resolve role/resonance/writeup into session- and participant-level dicts."""
        from world.magic.models.affinity import Resonance  # noqa: PLC0415

        session_kwargs: dict[str, Any] = {}
        initiator_participant_kwargs: dict[str, Any] = {}

        role_token = kwargs.get("role", "")
        resonance_token = kwargs.get("resonance", "")
        writeup = kwargs.get("writeup", "")

        if role_token:
            initiator_participant_kwargs[_PARTICIPANT_ROLE_KEY] = _resolve_soul_tether_role(
                role_token
            )
        if resonance_token:
            resonance_name = resonance_token.strip()
            resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
            if resonance is None:
                msg = f"No resonance named '{resonance_name}'."
                raise CommandError(msg)
            session_kwargs[_SESSION_RESONANCE_ID_KEY] = resonance.pk
        if writeup:
            session_kwargs[_SESSION_WRITEUP_KEY] = writeup

        return DraftParse(
            session_kwargs=session_kwargs,
            session_references=[],
            initiator_participant_kwargs=initiator_participant_kwargs,
            initiator_references=[],
        )

    def parse_join(self, *, kwargs: dict[str, str], caller: Any) -> JoinParse:
        """Resolve role into a participant-level dict."""
        participant_kwargs: dict[str, Any] = {}
        role_token = kwargs.get("role", "")
        if role_token:
            participant_kwargs[_PARTICIPANT_ROLE_KEY] = _resolve_soul_tether_role(role_token)
        return JoinParse(participant_kwargs=participant_kwargs, references=[])


# ---------------------------------------------------------------------------
# Covenant induction adapter
# ---------------------------------------------------------------------------

_COVENANT_INDUCTION_SERVICE_PATH = "world.covenants.services.induct_member_via_session"


class CovenantInductionAdapter(RitualDraftAdapter):
    """Adapter for the covenant INDUCTION session ritual.

    Translates ``covenant=`` (draft) and ``role=`` (join) tokens into the
    ``RitualSessionReferenceSpec`` rows that ``induct_member_via_session`` and
    ``assert_initiator_can_induct`` expect.
    """

    def parse_draft(self, *, kwargs: dict[str, str], caller: Any) -> DraftParse:
        """Resolve ``covenant=`` into a session-level COVENANT reference."""
        from world.covenants.models import Covenant  # noqa: PLC0415
        from world.magic.constants import ReferenceKind  # noqa: PLC0415

        covenant_name = kwargs.get("covenant", "").strip()
        covenant = Covenant.objects.filter(name__iexact=covenant_name).first()
        if covenant is None:
            msg = f"No covenant named '{covenant_name}'."
            raise CommandError(msg)
        return DraftParse(
            session_references=[
                RitualSessionReferenceSpec(kind=ReferenceKind.COVENANT, ref_covenant=covenant)
            ],
        )

    def parse_join(self, *, kwargs: dict[str, str], caller: Any) -> JoinParse:
        """Resolve ``role=`` into a participant-level COVENANT_ROLE reference."""
        from world.covenants.models import CovenantRole  # noqa: PLC0415
        from world.magic.constants import ReferenceKind  # noqa: PLC0415

        role_name = kwargs.get("role", "").strip()
        role = CovenantRole.objects.filter(name__iexact=role_name).first()
        if role is None:
            msg = f"No covenant role named '{role_name}'."
            raise CommandError(msg)
        return JoinParse(
            references=[
                RitualSessionReferenceSpec(kind=ReferenceKind.COVENANT_ROLE, ref_covenant_role=role)
            ],
        )


# ---------------------------------------------------------------------------
# Banner-call (battle covenant rise) adapter
# ---------------------------------------------------------------------------

_BANNER_CALL_SERVICE_PATH = "world.covenants.services.rise_battle_covenant_via_session"


class BannerCallAdapter(RitualDraftAdapter):
    """Adapter for the 'call the banners' battle-covenant rise ritual.

    Translates ``covenant=`` (draft) into a session-level COVENANT reference.
    Join requires no additional tokens — members simply accept.

    ``rise_battle_covenant_via_session`` reads only the session-level COVENANT
    reference; it does not consume any ``session_kwargs``, so none are set here.
    """

    def parse_draft(self, *, kwargs: dict[str, str], caller: Any) -> DraftParse:
        """Resolve ``covenant=`` into a session-level COVENANT reference."""
        from world.covenants.models import Covenant  # noqa: PLC0415
        from world.magic.constants import ReferenceKind  # noqa: PLC0415

        covenant_name = kwargs.get("covenant", "").strip()
        covenant = Covenant.objects.filter(name__iexact=covenant_name).first()
        if covenant is None:
            msg = f"No covenant named '{covenant_name}'."
            raise CommandError(msg)
        return DraftParse(
            session_references=[
                RitualSessionReferenceSpec(kind=ReferenceKind.COVENANT, ref_covenant=covenant)
            ],
        )


# ---------------------------------------------------------------------------
# Registry and lookup
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, RitualDraftAdapter] = {
    _SOUL_TETHER_SERVICE_PATH: SoulTetherAdapter(),
    _COVENANT_INDUCTION_SERVICE_PATH: CovenantInductionAdapter(),
    _BANNER_CALL_SERVICE_PATH: BannerCallAdapter(),
}
_DEFAULT_ADAPTER = RitualDraftAdapter()


def get_adapter(ritual: Ritual) -> RitualDraftAdapter:
    """Return the draft/join adapter for the given ritual.

    Keys on ``ritual.service_function_path``; returns the base no-op adapter
    when the ritual is not registered.
    """
    return _REGISTRY.get(ritual.service_function_path, _DEFAULT_ADAPTER)
