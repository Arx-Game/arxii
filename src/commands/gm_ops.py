"""Telnet ``gm dashboard`` + ``gm idle`` commands (#2004).

Thin over the same services the web ``GMDashboardView`` and
``StaffWorkloadView`` call. ``gm dashboard`` is GM-gated; ``gm idle`` is
staff-only (``perm(Admin)``).

``gm check``/``gm award``/``gm condition`` (#2118) are the GM adjudication
toolkit's telnet face — thin ``resolve_action_args()``-style parsing +
``action.run()`` over ``InvokeCatalogCheckAction``/``GMAwardAction``/
``GMApplyConditionAction`` (``actions/definitions/gm_adjudication.py``), the
same seam the web available-actions dispatcher uses. ``gm condition remove
<character> condition=<name> reason=<text>`` (#3431) is the referee off-switch
``GMApplyConditionAction`` never got — dispatches ``GMRemoveConditionAction``,
catalog-bounded to the target's own active instances.

``gm dramatic <character> reason=<text>`` (#3387) is the SENIOR-gated manual
dramatic-beat trigger — thin over ``GMTriggerDramaticBeatAction``
(``actions/definitions/gm_combat.py``), a staff/senior stopgap for a beat none
of the automatic surge detectors catch.

``gm suggest <kind>=<text>`` (#2127) is the scenario catalog's suggestion
inbox verb — thin over ``SubmitCatalogSuggestionAction``
(``actions/definitions/gm_catalog.py``), landing in the same staff inbox
``GMApplication`` already routes through.

``gm npc <name>[=<description>] [preset=<name>]`` (#3426; ``preset=`` #3427)
is the GM story-NPC on-ramp — thin over ``MintStoryNPCAction``
(``actions/definitions/gm_npcs.py``), which mints a Story NPC tenure-bound to
the caller's own account so the persona picker and ``@ic`` work on it
immediately. ``preset=<name>`` names a curated ``NPCStatlinePreset`` by
natural key, giving the NPC a real, rollable statline at mint time instead of
a blank sheet.

``gm prompts`` / ``gm prompt send|dismiss|done <id>`` (#4101) is the telnet
face of the GM narration-prompt queue -- thin over
``world.gm.prompt_services`` + ``EmitAction``/``PemitAction``/
``DismissGMPromptAction``. ``gm prompts`` lists PENDING and NARRATED prompts
addressed to the caller (narrated ones marked); ``gm prompt send <id>``
narrates both of a prompt's authored defaults (private via pemit, room via
emit, each linked and skipping a blank one) and then closes the prompt itself
(R12-1 -- every line it sent is already covered, so closing releases nothing
extra and no separate ``done`` is needed); ``gm prompt dismiss <id>`` /
``gm prompt done <id>`` both close a prompt outright (``done`` is the GM-facing
name for closing a prompt that has already been narrated -- same action as
dismiss, R6-2). A dramatic-moment row is labelled with the ``moment
confirm|dismiss <id>`` verbs that resolve it (#4101 final review, B7), rather
than ``gm prompt`` growing a second dispatch path for that kind. The dashboard's own render gains a
``Narration prompts waiting: N`` line counting PENDING + NARRATED prompts
addressed to the caller.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags
from commands.utils.gm_resolution import resolve_character_sheet_in_room

_USAGE_DASHBOARD = "Usage: gm dashboard"
_USAGE_IDLE = "Usage: gm idle"
_USAGE_CLAIM = "Usage: gm claim <request-id>"
_USAGE_CHECK = (
    "Usage: gm check [find <term>] | gm check <character> <check-type>=<band>"
    " [edge=<reason>|setback=<reason>]"
    " (requires Senior GM+; use 'setsituation' for consequential checks)"
)
_USAGE_AWARD = (
    "Usage: gm award <character> xp=<amount> [reason=<text>]"
    " | gm award <character> dev=<trait> amount=<n> [reason=<text>]"
    " | gm award <character> hare=<organization> reason=<text>"
    " | gm award <character> stat=<trait>"
    " | gm award <character> technique=<name>"
)
_USAGE_CONDITION = (
    "Usage: gm condition <character> condition=<name> [severity=<n>] [duration=<n>] [note=<text>]"
    " | gm condition remove <character> condition=<name> reason=<text>"
)
_USAGE_DRAMATIC = "Usage: gm dramatic <character> reason=<text> (requires Senior GM+)"
_USAGE_SUGGEST = (
    "Usage: gm suggest <kind>=<text>"
    " (kind: new_situation|check_fit|difficulty_guide|pool_guide|other)"
)
_USAGE_TRAP = "Usage: gm trap list | gm trap arm <id> | gm trap disarm <id>"
_USAGE_SUMMON = (
    "Usage: gm summon <character>"
    " (consent-prompted -- the character must `accept summon`/`decline summon`)"
)
_USAGE_NPC = "Usage: gm npc <name>[=<description>] [preset=<name>] (requires Junior GM+)"
_USAGE_PROMPT = (
    "Usage: gm prompt send <id> | gm prompt dismiss <id> | gm prompt done <id>"
    " | gm prompt confirm <id> | gm prompt hold <id> | gm prompt override <id> <reason>"
    " | gm prompt answer <id> [answer=<answer id> | text=<your words> [clue=<clue id>]]"
)
_USAGE_STANDOFF = "Usage: gm standoff shake <group> <reason> | gm standoff steady <group> <reason>"
_SUBVERB_LIST = "list"
_SUBVERB_ARM = "arm"
_SUBVERB_DISARM = "disarm"
_SUBVERB_REMOVE = "remove"
_PROMPT_SEND = "send"
_PROMPT_DISMISS = "dismiss"
_PROMPT_DONE = "done"
_PROMPT_ANSWER = "answer"
_KEY_ANSWER = "answer"
_KEY_TEXT = "text"
_KEY_CLUE = "clue"
# Standoff proposal decisions (#4354): verb -> registry action key.
_PROMPT_STANDOFF_VERBS: dict[str, str] = {
    "confirm": "gm_standoff_confirm",
    "hold": "gm_standoff_hold",
    "override": "gm_standoff_override",
}

# parse_kv_and_flags key names -- module constants so the STRING_LITERAL lint's
# comparison/membership check doesn't see bare identifier-shaped literals.
_KEY_XP = "xp"
_KEY_DEV = "dev"
_KEY_HARE = "hare"
_KEY_STAT = "stat"
_KEY_TECHNIQUE = "technique"
_KEY_SEVERITY = "severity"
_KEY_DURATION = "duration"
_KEY_NOTE = "note"


def _prompt_subject(prompt: Any, names: dict[int, str]) -> str:
    """Who or what a prompt row is about: its subject, the stake, or the standoff group."""
    if names[prompt.pk]:
        return names[prompt.pk]
    if prompt.stake_outcome_id:
        return prompt.stake_outcome.stake.player_summary
    if prompt.standoff_group_id is not None:
        return prompt.standoff_group.name
    return ""


class CmdGMDashboard(ArxCommand):
    """Show the GM dashboard: tables, sessions, stories needing attention (#2004).

    Usage:
      gm dashboard
      gm claim <request-id>
      gm check [find <term>]                    (requires Senior GM+)
      gm check <character> <check-type>=<band>  [edge=<reason>|setback=<reason>]
        (requires Senior GM+; use 'setsituation' for consequential checks)
      gm award <character> xp=<amount> [reason=<text>]
      gm award <character> dev=<trait> amount=<n> [reason=<text>]
      gm award <character> hare=<organization> reason=<text>
      gm award <character> stat=<trait>
      gm award <character> technique=<name>
      gm condition <character> condition=<name> [severity=<n>] [duration=<n>] [note=<text>]
      gm condition remove <character> condition=<name> reason=<text>
      gm dramatic <character> reason=<text>     (requires Senior GM+)
      gm suggest <kind>=<text>
      gm trap list
      gm trap arm <id>
      gm trap disarm <id>
      gm summon <character>
      gm npc <name>[=<description>] [preset=<name>]  (requires Junior GM+)
      gm prompts
      gm prompt send <id>
      gm prompt dismiss <id>
      gm prompt done <id>
      gm prompt confirm <id>                    (standoff: they attack)
      gm prompt hold <id>                       (standoff: test again after the next action)
      gm prompt override <id> <reason>          (standoff: they stay in the standoff)
      gm prompt answer <id>                     (a stewarded being: list what you can send)
      gm prompt answer <id> answer=<answer id>  (send one of the being's answers)
      gm prompt answer <id> text=<words> [clue=<clue id>]
                                                (your own words, Success and above)
      gm standoff shake <group> <reason>        (one morale state down)
      gm standoff steady <group> <reason>       (one morale state up)
    """

    key = "gm"
    aliases = ("gmdashboard",)
    locks = "cmd:all()"
    help_category = "GM"
    action = None

    def func(self) -> None:
        """Route the leading subverb, falling back to the dashboard render.

        A dispatch dict (not an if/elif chain) keeps this under the cyclomatic
        complexity budget as subverbs accumulate (#3426 added the 9th, tipping
        an elif chain over the C901 threshold).
        """
        try:
            raw = (self.args or "").strip()
            tokens = raw.split(maxsplit=1)
            first = tokens[0].lower() if tokens else ""
            rest = tokens[1].strip() if len(tokens) > 1 else ""
            handlers = {
                "claim": self._claim,
                "check": self._handle_check,
                "award": self._handle_award,
                "condition": self._handle_condition,
                "dramatic": self._handle_dramatic,
                "suggest": self._handle_suggest,
                "trap": self._handle_trap,
                "summon": self._handle_summon,
                "npc": self._handle_npc,
                "prompts": self._list_prompts,
                "prompt": self._handle_prompt,
                "standoff": self._handle_standoff,
            }
            handler = handlers.get(first)
            if handler is None:
                self._render()
            else:
                handler(rest)
        except CommandError as err:
            self.msg(str(err))

    def _claim(self, rest: str) -> None:
        """``gm claim <request-id>`` — claim an open group story request (#2119)."""
        rest = rest.strip()
        if not rest.isdigit():
            raise CommandError(_USAGE_CLAIM)
        from actions.definitions.gm_stories import ClaimGroupStoryRequestAction  # noqa: PLC0415

        result = ClaimGroupStoryRequestAction().run(actor=self.caller, request_id=int(rest))
        self.msg(result.message)

    def _resolve_target(self, name: str) -> Any:
        """Resolve a co-located character by name; raises CommandError if absent."""
        room = self.caller.location
        if room is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        sheet = resolve_character_sheet_in_room(self.caller, name, room=room)
        return sheet.character

    def _handle_check(self, rest: str) -> None:
        """Dispatch InvokeCatalogCheckAction -- find/list mode or invoke mode."""
        from actions.definitions.gm_adjudication import InvokeCatalogCheckAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        first = tokens[0] if tokens else ""
        if first in ("", "find"):  # noqa: STRING_LITERAL
            query = tokens[1].strip() if len(tokens) > 1 else ""
            result = InvokeCatalogCheckAction().run(actor=self.caller, query=query)
            if result.message:
                self.msg(result.message)
            return

        char_name = first
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        # The check-type reference IS the key (e.g. "Grapple=hard") -- it can't be
        # pre-registered as a multiword key since it's arbitrary/unknown ahead of
        # parsing, so a multi-word check name must be referenced by pk here (mirrors
        # the documented multi-word-name limitation in parse_targets_from_text).
        try:
            kwargs, _flags = parse_kv_and_flags(
                kv_rest,
                multiword_keys=frozenset({"edge", "setback"}),
                known_flags=frozenset(),
            )
        except CommandError:
            raise CommandError(_USAGE_CHECK) from None
        edge_reason = kwargs.pop("edge", None)
        setback_reason = kwargs.pop("setback", None)
        if len(kwargs) != 1:
            raise CommandError(_USAGE_CHECK)
        ((check_type_ref, difficulty),) = kwargs.items()

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {
            "target": target,
            "check_type_ref": check_type_ref,
            "difficulty": difficulty,
        }
        if edge_reason:
            run_kwargs["edge_reason"] = edge_reason
        if setback_reason:
            run_kwargs["setback_reason"] = setback_reason

        result = InvokeCatalogCheckAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_award(self, rest: str) -> None:
        """Dispatch GMAwardAction -- xp=<amount>, dev=<trait> amount=<n>, hare=<org>,
        stat=<trait>, or technique=<name>."""
        from actions.definitions.gm_adjudication import GMAwardAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_AWARD)
        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        # dev=/stat= trait refs are single-word only (mirrors the check-type-ref
        # multiword limitation) -- a multi-word trait name must be referenced by
        # pk. technique= names commonly ARE multi-word (e.g. "Ember Lance"), so
        # it gets multiword consumption like reason=/hare=.
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"reason", _KEY_HARE, _KEY_TECHNIQUE}),
            known_flags=frozenset(),
        )
        reason = kwargs.pop("reason", "")

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {"target": target, "description": reason}
        if _KEY_XP in kwargs:
            run_kwargs["award_type"] = "xp"
            run_kwargs["amount"] = kwargs[_KEY_XP]
        elif _KEY_DEV in kwargs:
            run_kwargs["award_type"] = "development"
            run_kwargs["trait_ref"] = kwargs[_KEY_DEV]
            run_kwargs["amount"] = kwargs.get("amount")
        elif _KEY_HARE in kwargs:
            run_kwargs["award_type"] = "favor_token"
            run_kwargs["org_ref"] = kwargs[_KEY_HARE]
        elif _KEY_STAT in kwargs:
            run_kwargs["award_type"] = "stat"
            run_kwargs["trait_ref"] = kwargs[_KEY_STAT]
        elif _KEY_TECHNIQUE in kwargs:
            run_kwargs["award_type"] = "technique"
            run_kwargs["technique_ref"] = kwargs[_KEY_TECHNIQUE]
        else:
            raise CommandError(_USAGE_AWARD)

        result = GMAwardAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_condition(self, rest: str) -> None:
        """``gm condition <character> condition=<name> [severity=][duration=][note=]``
        dispatches ``GMApplyConditionAction``; ``gm condition remove <character>
        condition=<name> reason=<text>`` dispatches ``GMRemoveConditionAction`` (#3431)."""
        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_CONDITION)
        if tokens[0].lower() == _SUBVERB_REMOVE:  # noqa: STRING_LITERAL
            self._handle_condition_remove(tokens[1].strip() if len(tokens) > 1 else "")
            return

        from actions.definitions.gm_adjudication import GMApplyConditionAction  # noqa: PLC0415

        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"condition", "note"}),
            known_flags=frozenset(),
        )
        condition_ref = kwargs.get("condition")
        if not condition_ref:
            raise CommandError(_USAGE_CONDITION)

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {
            "target": target,
            "condition_ref": condition_ref,
        }
        if _KEY_SEVERITY in kwargs:
            run_kwargs["severity"] = kwargs[_KEY_SEVERITY]
        if _KEY_DURATION in kwargs:
            run_kwargs["duration_rounds"] = kwargs[_KEY_DURATION]
        if _KEY_NOTE in kwargs:
            run_kwargs["note"] = kwargs[_KEY_NOTE]

        result = GMApplyConditionAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_condition_remove(self, rest: str) -> None:
        """``gm condition remove <character> condition=<name> reason=<text>`` (#3431)."""
        from actions.definitions.gm_adjudication import GMRemoveConditionAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_CONDITION)
        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"condition", "reason"}),
            known_flags=frozenset(),
        )
        condition_ref = kwargs.get("condition")
        reason = kwargs.get("reason")
        if not condition_ref or not reason:
            raise CommandError(_USAGE_CONDITION)

        target = self._resolve_target(char_name)
        result = GMRemoveConditionAction().run(
            actor=self.caller, target=target, condition=condition_ref, reason=reason
        )
        if result.message:
            self.msg(result.message)

    def _handle_dramatic(self, rest: str) -> None:
        """Dispatch GMTriggerDramaticBeatAction -- reason=<text> (#3387, Senior GM+)."""
        from actions.definitions.gm_combat import GMTriggerDramaticBeatAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_DRAMATIC)
        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"reason"}),
            known_flags=frozenset(),
        )
        reason = kwargs.get("reason")
        if not reason:
            raise CommandError(_USAGE_DRAMATIC)

        target = self._resolve_target(char_name)
        result = GMTriggerDramaticBeatAction().run(actor=self.caller, target=target, reason=reason)
        if result.message:
            self.msg(result.message)

    def _handle_suggest(self, rest: str) -> None:
        """Dispatch SubmitCatalogSuggestionAction -- <kind>=<text> (#2127)."""
        from actions.definitions.gm_catalog import SubmitCatalogSuggestionAction  # noqa: PLC0415

        if "=" not in rest:
            raise CommandError(_USAGE_SUGGEST)
        kind, _, text = rest.partition("=")
        proposal_kind = kind.strip().lower()
        proposal_text = text.strip()
        if not proposal_kind or not proposal_text:
            raise CommandError(_USAGE_SUGGEST)

        result = SubmitCatalogSuggestionAction().run(
            actor=self.caller,
            proposal_kind=proposal_kind,
            proposal_text=proposal_text,
        )
        if result.message:
            self.msg(result.message)

    def _handle_trap(self, rest: str) -> None:
        """``gm trap list|arm <id>|disarm <id>`` - manage traps in this room (#3002).

        Thin: parse the subverb and the id, then hand off. Authorization lives
        entirely in the Actions' prerequisites, like every other subverb here.
        """
        from actions.definitions.traps import (  # noqa: PLC0415
            ArmTrapAction,
            GmDisarmTrapAction,
            ListRoomTrapsAction,
        )

        tokens = rest.split(maxsplit=1)
        subverb = tokens[0].lower() if tokens else ""
        argument = tokens[1].strip() if len(tokens) > 1 else ""

        if subverb == _SUBVERB_LIST:
            result = ListRoomTrapsAction().run(actor=self.caller)
            self.msg(result.message)
            return

        if subverb not in (_SUBVERB_ARM, _SUBVERB_DISARM) or not argument.isdigit():
            raise CommandError(_USAGE_TRAP)

        action = ArmTrapAction() if subverb == _SUBVERB_ARM else GmDisarmTrapAction()
        result = action.run(actor=self.caller, trap_id=int(argument))
        self.msg(result.message)

    def _handle_summon(self, rest: str) -> None:
        """``gm summon <character>`` -- consent-prompted GM summon (#3071).

        The target need not be co-located (the whole point of a summon), so this
        resolves globally rather than via the room-scoped ``_resolve_target``
        every other subverb here uses.
        """
        from actions.definitions.gm_adjudication import SummonPlayerAction  # noqa: PLC0415

        name = rest.strip()
        if not name:
            raise CommandError(_USAGE_SUMMON)
        target = self.caller.search(name, global_search=True)
        if not target:
            return

        result = SummonPlayerAction().run(actor=self.caller, target=target)
        if result.message:
            self.msg(result.message)

    def _handle_npc(self, rest: str) -> None:
        """``gm npc <name>[=<description>] [preset=<name>]`` -- mint a Story NPC
        (#3426, Junior GM+; ``preset=`` selects a curated statline, #3427).

        ``preset=<name>`` is pulled off the tail before the name/description
        split (which still runs on the first bare ``=``, unchanged from
        #3426) so a preset can be combined with a description:
        ``gm npc Bob=A grim watchman. preset=Guard``.
        """
        from actions.definitions.gm_npcs import MintStoryNPCAction  # noqa: PLC0415

        preset_name = ""
        marker = " preset="
        marker_index = rest.find(marker)
        if marker_index != -1:
            preset_name = rest[marker_index + len(marker) :].strip()
            rest = rest[:marker_index]

        npc_name, _, description = rest.partition("=")
        npc_name = npc_name.strip()
        if not npc_name:
            raise CommandError(_USAGE_NPC)

        run_kwargs: dict[str, Any] = {
            "name": npc_name,
            "description": description.strip(),
        }
        if preset_name:
            run_kwargs["preset"] = preset_name

        result = MintStoryNPCAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _list_prompts(self, _rest: str = "") -> None:
        """``gm prompts`` -- PENDING and NARRATED prompts visible to the caller
        in whatever scene is active where they stand (#4101). Controller
        amendment R6-2: a NARRATED prompt stays listed, marked as such, until
        the GM closes it with ``send``/``dismiss``/``done``. Ruling R12-2: one
        visibility source -- ``visible_prompts_for_location`` defers entirely to
        ``visible_prompts_for``, the same function the REST queue
        (``GET /api/gm/prompts/?scene=``) uses, so a muted GM, or one standing
        outside any scene, sees on telnet exactly what the web would show.
        """
        from world.gm.constants import GMPromptStatus  # noqa: PLC0415
        from world.gm.prompt_services import (  # noqa: PLC0415
            prompt_subject_names,
            prompt_telnet_commands,
            visible_prompts_for_location,
        )

        account = self.caller.account
        prompts = list(visible_prompts_for_location(account, self.caller.location))
        if not prompts:
            self.msg("No GM prompts are waiting.")
            return
        names = prompt_subject_names(prompts, account, viewer_sheet=self.caller.character_sheet)
        for p in prompts:
            subject = _prompt_subject(p, names)
            status_tag = " (narrated)" if p.status == GMPromptStatus.NARRATED else ""
            self.msg(f"[{p.pk}] {p.get_kind_display()}{status_tag}: {subject}")
            if p.standoff_group_id is not None:
                from world.standoffs.services.proposals import (  # noqa: PLC0415
                    proposal_summary,
                )

                self.msg(f"  {proposal_summary(p.standoff_group)}")
            if p.pledge_id is not None:
                from world.worship.steward_services import prompt_summary  # noqa: PLC0415

                self.msg(f"  {prompt_summary(p)}")
            if p.private_text:
                self.msg(f"  private: {p.private_text}")
            if p.room_text:
                self.msg(f"  room: {p.room_text}")
            self.msg(f"  {prompt_telnet_commands(p)}")

    def _handle_prompt(self, rest: str) -> None:
        """``gm prompt send|dismiss|done <id>`` (#4101).

        ``done`` is the GM-facing name for closing a prompt that has already
        been narrated -- the same close action as ``dismiss`` (R6-2).
        """
        verb, _, raw_id = rest.partition(" ")
        verb = verb.strip().lower()
        raw_id = raw_id.strip()
        if verb in _PROMPT_STANDOFF_VERBS:
            self._decide_standoff_prompt(verb, raw_id)
            return
        if verb == _PROMPT_ANSWER:
            self._answer_being_prompt(raw_id)
            return
        if verb not in (_PROMPT_SEND, _PROMPT_DISMISS, _PROMPT_DONE) or not raw_id.isdigit():
            raise CommandError(_USAGE_PROMPT)
        prompt_id = int(raw_id)
        if verb in (_PROMPT_DISMISS, _PROMPT_DONE):
            self._dismiss_prompt(prompt_id)
            return
        self._send_prompt_defaults(prompt_id)

    def _answer_being_prompt(self, rest: str) -> None:
        """``gm prompt answer <id> [answer=<n> | text=<words> [clue=<n>]]`` (#4333 slice 4).

        With no choice it lists what the steward can send: the being's answers at
        or below the tier, whether their own text is allowed, and the clues they
        may attach. A choice dispatches ``AnswerBeingPromptAction``.
        """
        from actions.definitions.worship import AnswerBeingPromptAction  # noqa: PLC0415

        raw_id, _, tail = rest.partition(" ")
        if not raw_id.isdigit():
            raise CommandError(_USAGE_PROMPT)
        prompt_id = int(raw_id)
        kwargs, _flags = parse_kv_and_flags(
            tail.strip(), multiword_keys=frozenset({_KEY_TEXT}), known_flags=frozenset()
        )
        if not kwargs:
            self._list_being_answer_options(prompt_id)
            return
        result = AnswerBeingPromptAction().run(
            actor=None,
            account=self.caller.account,
            prompt_id=prompt_id,
            answer_id=kwargs.get(_KEY_ANSWER),
            text=kwargs.get(_KEY_TEXT, ""),
            clue_id=kwargs.get(_KEY_CLUE),
        )
        self.msg(result.message or "Done.")

    def _list_being_answer_options(self, prompt_id: int) -> None:
        from world.gm.constants import GMPromptKind  # noqa: PLC0415
        from world.gm.models import GMPrompt  # noqa: PLC0415
        from world.gm.prompt_services import prompt_visible_to  # noqa: PLC0415
        from world.worship.steward_services import (  # noqa: PLC0415
            answer_options,
            answer_window_ends,
            catalogue_clues,
            may_write_free_text,
            prompt_summary,
        )

        prompt = GMPrompt.objects.filter(pk=prompt_id, kind=GMPromptKind.BEING_ANSWER).first()
        account = self.caller.account
        if prompt is None or not prompt_visible_to(account, prompt) or prompt.pledge is None:
            msg = "There is no such being answer prompt."
            raise CommandError(msg)
        details = prompt.pledge
        self.msg(prompt_summary(prompt))
        self.msg(f"  Pledge: {details.pledge.name}.")
        if details.prayer is not None:
            self.msg(f"  Prayer: {details.prayer.text}")
        for answer in answer_options(details):
            first = (answer.answer_text or answer.delay_text).strip().splitlines()[0][:80]
            self.msg(f"  answer={answer.pk} ({answer.outcome_tier.name}) {first}")
        if may_write_free_text(details):
            clues = catalogue_clues(details.pledge.being)
            clue_text = ", ".join(f"clue={c.pk} {c.name}" for c in clues) or "none linked"
            self.msg(f"  text=<your words> is allowed. Clues you may attach: {clue_text}.")
        else:
            self.msg("  Your own text is allowed on Success and Critical Success only.")
        ends = answer_window_ends(prompt)
        self.msg(
            f"  Dismissed or unanswered by {ends:%Y-%m-%d %H:%M}, an authored answer is drawn."
        )

    def _decide_standoff_prompt(self, verb: str, rest: str) -> None:
        """``gm prompt confirm|hold <id>`` / ``gm prompt override <id> <reason>`` (#4354)."""
        from actions.registry import get_action  # noqa: PLC0415

        raw_id, _, reason = rest.partition(" ")
        if not raw_id.isdigit():
            raise CommandError(_USAGE_PROMPT)
        action = get_action(_PROMPT_STANDOFF_VERBS[verb])
        result = action.run(
            actor=None,
            account=self.caller.account,
            prompt_id=int(raw_id),
            reason=reason.strip(),
        )
        self.msg(result.message or "Done.")

    def _handle_standoff(self, rest: str) -> None:
        """``gm standoff shake|steady <group> <reason>`` (#4354): the GM morale control.

        ``<group>`` is the group's id (shown by ``standoff``) or its creature's name, scoped
        to the standoff in the caller's room.
        """
        from actions.definitions.gm_standoff import GMStandoffMoraleAction  # noqa: PLC0415
        from commands.standoff import _room_standoff_encounter  # noqa: PLC0415
        from world.standoffs.constants import MoraleDirection  # noqa: PLC0415

        direction, _, tail = rest.partition(" ")
        direction = direction.strip().lower()
        if direction not in MoraleDirection.values or not tail.strip():
            raise CommandError(_USAGE_STANDOFF)
        encounter = _room_standoff_encounter(self.caller)
        if encounter is None:
            msg = "There is no standoff here."
            raise CommandError(msg)
        group, reason = self._standoff_group_and_reason(encounter, tail.strip())
        result = GMStandoffMoraleAction().run(
            actor=None,
            account=self.caller.account,
            group_id=group.pk,
            direction=direction,
            reason=reason,
        )
        self.msg(result.message or "Done.")

    @staticmethod
    def _standoff_group_and_reason(encounter: Any, text: str) -> tuple[Any, str]:
        """Split ``<group> <reason>``: a leading id, or the longest leading group name."""
        groups = list(encounter.standoff_groups.select_related("creature_template"))
        head, _, tail = text.partition(" ")
        if head.isdigit():
            match = next((g for g in groups if g.pk == int(head)), None)
            if match is not None:
                return match, tail.strip()
        words = text.split()
        for cut in range(len(words) - 1, 0, -1):
            name = " ".join(words[:cut]).lower()
            match = next((g for g in groups if g.creature_template.name.lower() == name), None)
            if match is not None:
                return match, " ".join(words[cut:])
        raise CommandError(_USAGE_STANDOFF)

    def _dismiss_prompt(
        self,
        prompt_id: int,
        *,
        fallback: str = "Dismissed; the authored text goes out on its own.",
    ) -> None:
        from actions.definitions.dramatic_moments import DismissGMPromptAction  # noqa: PLC0415

        result = DismissGMPromptAction().run(
            actor=None, account=self.caller.account, prompt_id=prompt_id
        )
        self.msg(result.message or fallback)

    def _send_prompt_defaults(self, prompt_id: int) -> None:
        """``gm prompt send <id>`` -- rulings R12-1 and R12-3 (#4101).

        Narrates whichever of a prompt's two authored defaults isn't already
        covered (skipping a blank one too), through the linked emit/pemit,
        then closes the prompt itself via the dismiss action. Every line it
        sends is covered by the time the close runs, so closing releases
        nothing extra and the GM never needs a separate ``done`` for a prompt
        sent through this verb.

        R12-3: coverage is read from ``prompt_narration_coverage`` -- the same
        computation ``_resolve_narration_prompt`` uses to decide what a close
        releases, never re-derived -- so re-running ``send`` after a partial
        failure (e.g. the room line landed, then something interrupted before
        the private one) narrates only the leg still missing.

        Fix round 1, finding 1: the private leg additionally checks the
        subject is physically present (``present_characters_in_room``, the
        same presence check ``NarrateGMPromptSerializer`` uses for the REST
        chosen-receiver audience) -- an absent subject skips the private line
        and tells the GM; the room line still goes out regardless.
        """
        from world.gm.models import GMPrompt  # noqa: PLC0415
        from world.gm.prompt_services import (  # noqa: PLC0415
            prompt_narration_coverage,
            prompt_visible_to,
        )

        prompt = (
            GMPrompt.objects.filter(pk=prompt_id)
            .select_related("character_sheet__character", "scene")
            .first()
        )
        if prompt is None or not prompt_visible_to(self.caller.account, prompt):
            # Fix round 1, minor 6: one neutral reply for both "doesn't exist"
            # and "exists but isn't yours" -- same IDOR-safe shape the REST
            # object lookup already uses.
            msg = "There is no such GM prompt."
            raise CommandError(msg)
        room_covered, private_covered = prompt_narration_coverage(prompt)
        if not private_covered and prompt.private_text.strip() and prompt.character_sheet_id:
            self._send_private_prompt_default(prompt)
        if not room_covered and prompt.room_text.strip():
            self._send_room_prompt_default(prompt)
        self._dismiss_prompt(prompt.pk, fallback="Sent and closed.")

    def _send_private_prompt_default(self, prompt: Any) -> None:
        """Send the prompt's private line when its subject is present."""
        from actions.definitions.communication import PemitAction  # noqa: PLC0415
        from world.gm.prompt_services import (  # noqa: PLC0415
            narration_location_for,
            present_characters_in_room,
            prompt_subject_name,
        )

        location = narration_location_for(prompt, self.caller)
        present = present_characters_in_room([prompt.character_sheet_id], location)
        subject_character = present.get(prompt.character_sheet_id)
        if subject_character is None:
            subject = prompt_subject_name(prompt) or "The subject"
            self.msg(
                f"{subject} isn't here; their private line goes out on its own"
                " when the prompt closes."
            )
            return
        result = PemitAction().run(
            actor=self.caller,
            text=prompt.private_text,
            receivers=[subject_character],
            gm_prompt_id=prompt.pk,
        )
        if not result.success:
            raise CommandError(result.message or "Action failed")

    def _send_room_prompt_default(self, prompt: Any) -> None:
        """Send the prompt's authored room line."""
        from actions.definitions.communication import EmitAction  # noqa: PLC0415

        result = EmitAction().run(actor=self.caller, text=prompt.room_text, gm_prompt_id=prompt.pk)
        if not result.success:
            raise CommandError(result.message or "Action failed")

    def _render(self) -> None:
        raw = (self.args or "").strip().lower()
        if raw and raw != "dashboard":  # noqa: STRING_LITERAL
            raise CommandError(_USAGE_DASHBOARD)
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = self.caller.account.gm_profile
        except GMProfile.DoesNotExist:
            msg = "You must have a GM profile to use this command."
            raise CommandError(msg) from None

        from world.gm.constants import GMTableStatus  # noqa: PLC0415
        from world.gm.models import GMTable  # noqa: PLC0415
        from world.gm.services import gm_evidence_summary  # noqa: PLC0415
        from world.stories.constants import (  # noqa: PLC0415
            StoryGMOfferStatus,
        )
        from world.stories.models import (  # noqa: PLC0415
            StoryGMOffer,
        )
        from world.stories.views import _collect_gm_queue  # noqa: PLC0415

        buckets = _collect_gm_queue(gm_profile)
        lines = ["GM Dashboard:"]
        lines.append(f"  Episodes ready to run: {len(buckets.episodes_ready)}")
        lines.append(f"  Pending AGM claims: {len(buckets.pending_claims)}")
        lines.append(f"  Assigned sessions: {len(buckets.assigned_requests)}")
        lines.append(f"  Stories waiting on you: {len(buckets.waiting_for_gm)}")

        my_tables = GMTable.objects.filter(gm=gm_profile, status=GMTableStatus.ACTIVE)
        lines.append(f"  Active tables: {my_tables.count()}")
        lines.extend(f"    [{table.pk}] {table.name}" for table in my_tables)

        pending_offers = StoryGMOffer.objects.filter(
            offered_to=gm_profile, status=StoryGMOfferStatus.PENDING
        ).count()
        lines.append(f"  Pending story offers: {pending_offers}")

        from world.gm.constants import GMPromptStatus  # noqa: PLC0415
        from world.gm.models import GMPrompt  # noqa: PLC0415

        # R6-2: the waiting count includes NARRATED prompts, not just PENDING --
        # a narrated-but-still-open prompt is still waiting on the GM to close it.
        waiting_prompts = GMPrompt.objects.filter(
            addressed_to=self.caller.account,
            status__in=(GMPromptStatus.PENDING, GMPromptStatus.NARRATED),
        ).count()
        lines.append(f"  Narration prompts waiting: {waiting_prompts}")

        lines.append(f"  Open group requests: {len(buckets.open_group_requests)}")
        lines.extend(
            f"    [{req['request_id']}] {req['covenant_name']}"
            for req in buckets.open_group_requests
        )

        evidence = gm_evidence_summary(gm_profile)
        lines.append(f"  Level: {evidence.level} | Stories running: {evidence.stories_running}")
        self.msg("\n".join(lines))


class CmdGMIdle(ArxCommand):
    """List idle GM tables (staff-only, #2004).

    Usage:
      gm idle
    """

    key = "gmidle"
    aliases = ()
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        """List idle tables whose GM hasn't been active recently."""
        from world.gm.services import idle_tables  # noqa: PLC0415

        tables = list(idle_tables())
        if not tables:
            self.msg("No idle tables.")
            return
        lines = [f"Idle tables ({len(tables)}):"]
        for table in tables:
            gm_name = table.gm.account.username
            last = table.gm.last_active_at
            last_str = last.strftime("%Y-%m-%d") if last else "never"
            lines.append(f"  [{table.pk}] {table.name} — GM: {gm_name} (last active: {last_str})")
        self.msg("\n".join(lines))
