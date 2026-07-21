"""Story telnet namespace: GM lifecycle actions + player self-service (#1495, #1853).

GM subverbs (complete/resolve/promote/mark) delegate directly to
``Action().run(actor=self.caller, **kwargs)`` and are gated by the story's
Lead GM or staff status in the backing action layer — unchanged from #1495.

Player subverbs (bare `story` / `list` / `beats` / `signoff`) are self-scoped
reads/mutations over the caller's own account — no GM/staff gate, mirroring
CmdGMTable's precedent of mixed permission tiers under one command namespace.

``protect``/``clearance`` (#2001 Task 7) are a thin ORM + service layer over
``world.stories.services.custody_clearance`` — there is no dedicated Action for
these (Task 6 built plain permission functions, not a permission-class-gated
Action), so authorization is replicated inline exactly matching the API's
permission classes (``IsProtectedSubjectStoryOwnerOrStaff`` /
``IsClearanceCustodianGM`` / ``IsClearanceRequesterGM`` /
``IsStaffForCustodyResolution`` / ``IsClearanceCustodianOrStaff`` /
``IsGMProfile``) so telnet cannot escalate past the web surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand
from commands.parsing import parse_kv_and_flags
from commands.utils.gm_resolution import (
    resolve_episode_or_error,
    resolve_numeric_beat_id_or_error,
    resolve_story_or_error,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.boundaries.models import TreasuredSubject
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMProfile
    from world.societies.models import Organization, Society
    from world.stories.models import (
        CrossoverInvite,
        CustodyClearance,
        Story,
        StoryProtectedSubject,
    )

_SignoffMatchT = TypeVar("_SignoffMatchT")

_USAGE = (
    "Usage: story <subcommand>\n"
    "  story                              — your active stories\n"
    "  story list                         — same as bare `story`\n"
    "  story beats <episode-id>           — beats in one of your active episodes\n"
    "  story signoff <beat-id> <subject> [withdraw]\n"
    "                                     — grant/withdraw a treasured sign-off\n"
    "  story complete <story-id>\n"
    "  story resolve <episode-id> [transition-id] [notes]\n"
    "  story promote <episode-id> <pitch|outline|plot>\n"
    "  story mark <beat-id> <success|failure> [notes]\n"
    "  story protect <story-id> add|remove|list ...  — custody protection (#2001)\n"
    "  story clearance request|grant|deny|escalate|resolve|revoke|list ...\n"
    "                                     — custody clearance lifecycle (#2001)\n"
    "  story impact <story-id>=<table|regional|world>\n"
    "                                     — set impact tier (Lead GM; #2003)\n"
    "  story review-status <story-id>     — tier + review state (#2003)\n"
    "  story surrender <story-id>          — GM surrenders oversight (#2004)"
)

_IMPACT_USAGE = "Usage: story impact <story-id>=<table|regional|world>"
_REVIEW_STATUS_USAGE = "Usage: story review-status <story-id>"
_SURRENDER_USAGE = "Usage: story surrender <story-id>"

_COMPLETE_USAGE = "Usage: story complete <story-id>"
_HIDDEN_BEAT_TITLE = "(Hidden Beat)"
_DEFAULT_BEAT_TITLE = "Beat"
_RESOLVE_USAGE = "Usage: story resolve <episode-id> [transition-id] [notes]"
_PROMOTE_USAGE = "Usage: story promote <episode-id> <pitch|outline|plot>"
_MARK_USAGE = "Usage: story mark <beat-id> <success|failure> [notes]"

_MIN_PROMOTE_TOKENS = 2
_MIN_MARK_TOKENS = 2
_MIN_SIGNOFF_TOKENS = 2  # beat-id + at least one subject token
_WITHDRAW_KEYWORD = "withdraw"

_MIN_RESOLVE_TOKENS = 2  # id + grant|deny

_PROTECT_USAGE = (
    "Usage:\n"
    "  story protect <story-id> add <kind>=<subject-ref> [beat=<id>] [notes=<text>]\n"
    "                                     — kind: npc_fate|personal_jeopardy|item|"
    "faction|org|society|location|custom\n"
    "                                     — org/society disambiguate faction when a name"
    " matches both\n"
    "  story protect <story-id> remove <protected-id>\n"
    "  story protect <story-id> list"
)
_CLEARANCE_USAGE = (
    "Usage:\n"
    "  story clearance request <kind>=<subject-ref> scope=<appear|harm|remove>"
    " [story=<id>] [message=<text>]\n"
    "                                     — kind: npc_fate|personal_jeopardy|item|"
    "faction|org|society|location|custom\n"
    "  story clearance request protected=<id> scope=<appear|harm|remove>"
    " [story=<id>] [message=<text>]\n"
    "  story clearance grant <id> [note=<text>]\n"
    "  story clearance deny <id> [note=<text>]\n"
    "  story clearance escalate <id>\n"
    "  story clearance resolve <id> grant|deny [note=<text>]\n"
    "  story clearance revoke <id>\n"
    "  story clearance list [pending]"
)
_GRANT_DENY_USAGE = "Usage: story clearance grant|deny <id> [note=<text>]"
_ESCALATE_USAGE = "Usage: story clearance escalate <id>"
_RESOLVE_CLEARANCE_USAGE = "Usage: story clearance resolve <id> grant|deny [note=<text>]"
_REVOKE_USAGE = "Usage: story clearance revoke <id>"
_NEEDS_GM_PROFILE = "You must have a GM profile to do that."

_CROSSOVER_USAGE = (
    "Usage:\n"
    "  story crossover invite <event-id> story=<id> [episode=<id>] [message=<text>]\n"
    "                                     — invite another GM's story into a shared event\n"
    "  story crossover accept <invite-id> [episode=<id>] [note=<text>]\n"
    "                                     — accept an invite (invited story's Lead GM only)\n"
    "  story crossover decline <invite-id> [note=<text>]\n"
    "                                     — decline an invite (invited story's Lead GM only)\n"
    "  story crossover withdraw <invite-id>\n"
    "                                     — rescind an invite you sent\n"
    "  story crossover list [pending]     — your sent + received invites"
)
_CROSSOVER_INVITE_USAGE = (
    "Usage: story crossover invite <event-id> story=<id> [episode=<id>] [message=<text>]"
)
_CROSSOVER_MULTIWORD_KEYS = frozenset({"message", "note"})

# Subject-kind keys accepted for `story protect ... add` / `story clearance request`'s
# identity path (#2001 Task 7) — mirrors StakeSubjectKind, minus CAMPAIGN_TRACK (not
# exposed to this grammar per the Task 7 brief). `org`/`society` are disambiguating
# aliases for `faction` (Task 7 review Fix 2) — used when a name matches both an
# Organization and a Society, mirroring gemit.py's explicit-switch spirit.
_SUBJECT_KIND_KEYS = frozenset(
    {"npc_fate", "personal_jeopardy", "item", "faction", "org", "society", "location", "custom"}
)
# Keys whose value may span multiple bare tokens (character/faction/custom names,
# free-text notes/messages) — mirrors journals.py/goals.py's free-text-runs-to-next-key
# convention (parse_kv_and_flags).
_PROTECT_ADD_MULTIWORD_KEYS = frozenset(
    {
        "npc_fate",
        "personal_jeopardy",
        "faction",
        "org",
        "society",
        "location",
        "custom",
        "notes",
    }
)
_CLEARANCE_REQUEST_MULTIWORD_KEYS = frozenset(
    {
        "npc_fate",
        "personal_jeopardy",
        "faction",
        "org",
        "society",
        "location",
        "custom",
        "message",
    }
)

_SUBVERB_HANDLERS: dict[str, str] = {
    "complete": "_handle_complete",
    "resolve": "_handle_resolve",
    "promote": "_handle_promote",
    "mark": "_handle_mark",
    "list": "_handle_list",
    "beats": "_handle_beats",
    "signoff": "_handle_signoff",
    "protect": "_handle_protect",
    "clearance": "_handle_clearance",
    "crossover": "_handle_crossover",
    "impact": "_handle_impact",
    "review-status": "_handle_review_status",
    "surrender": "_handle_surrender",
}


class CmdStory(ArxNamespaceCommand):
    """Manage story episodes and beats.

    All subcommands are gated by the story's Lead GM or staff status in the
    backing action layer.
    """

    key = "story"
    aliases = ()
    locks = "cmd:all()"
    _USAGE = _USAGE
    _SUBVERB_HANDLERS = _SUBVERB_HANDLERS

    def func(self) -> None:
        """Bare `story` is the player's active-stories listing; else route by subverb."""
        raw = (self.args or "").strip()
        if not raw:
            self._handle_list("")
            return
        super().func()

    def _handle_list(self, rest: str) -> None:
        """Show the caller's active stories across all three scopes (#1853)."""
        from world.stories.services.dashboards import active_stories_for_account  # noqa: PLC0415

        result = active_stories_for_account(self.caller.account)
        entries = [
            *result["character_stories"],
            *result["group_stories"],
            *result["global_stories"],
        ]
        if not entries:
            self.msg("You have no active stories.")
            return
        lines = ["Your active stories:"]
        for entry in entries:
            episode_bit = (
                f' — currently in "{entry["current_episode_title"]}"'
                if entry["current_episode_title"]
                else ""
            )
            lines.append(
                f"  [{entry['story_id']}] {entry['story_title']}{episode_bit} "
                f"({entry['status_label']})"
            )
        self.msg("\n".join(lines))

    def _handle_beats(self, rest: str) -> None:
        """List a caller's-own-active-episode's beats, flagging pending sign-offs (#1853)."""
        from world.stories.models import Beat  # noqa: PLC0415
        from world.stories.services.boundaries import (  # noqa: PLC0415
            player_pending_treasured_signoffs,
        )
        from world.stories.services.dashboards import active_stories_for_account  # noqa: PLC0415

        episode_id = self._require_arg(rest, "Usage: story beats <episode-id>.")
        if not episode_id.isdigit():
            msg = "An episode must be specified by its numeric ID."
            raise CommandError(msg)

        result = active_stories_for_account(self.caller.account)
        my_episode_ids = {
            entry["current_episode_id"]
            for entry in (
                *result["character_stories"],
                *result["group_stories"],
                *result["global_stories"],
            )
            if entry["current_episode_id"] is not None
        }
        if int(episode_id) not in my_episode_ids:
            msg = "That's not one of your active stories."
            raise CommandError(msg)

        beats = list(Beat.objects.filter(episode_id=episode_id).order_by("order"))
        if not beats:
            self.msg("No beats yet for that episode.")
            return

        # account is None for an unpuppeted/possessed object; player_data itself
        # is a get-or-create property that never returns None on a real Account.
        account = self.caller.account
        player_data = account.player_data if account else None
        pending_by_beat: dict[int, tuple[int, ...]] = {}
        if player_data is not None:
            for entry in player_pending_treasured_signoffs(player_data, beats):
                pending_by_beat[entry.beat_id] = entry.treasured_subject_ids

        from world.boundaries.models import TreasuredSubject  # noqa: PLC0415

        pending_subject_ids = {tid for ids in pending_by_beat.values() for tid in ids}
        label_by_id = dict(
            TreasuredSubject.objects.filter(pk__in=pending_subject_ids).values_list(
                "pk", "subject_label"
            )
        )

        lines = ["Beats:"]
        for beat in beats:
            title = self._beat_title(beat)
            outcome = beat.outcome or "unsatisfied"
            line = f"  [{beat.pk}] {title} ({outcome})"
            for tid in pending_by_beat.get(beat.pk, ()):
                line += f"\n      SIGN-OFF NEEDED: {label_by_id.get(tid, '(unknown)')}"
            lines.append(line)
        self.msg("\n".join(lines))

    @staticmethod
    def _beat_title(beat: Any) -> str:
        """Resolve the display title for a beat based on its hint and visibility.

        Args:
            beat: A ``Beat`` object with ``player_hint`` and ``visibility`` attributes.

        Returns:
            The player hint if non-empty, "(Hidden Beat)" for secret beats, else "Beat".
        """
        from world.stories.constants import BeatVisibility  # noqa: PLC0415

        if beat.player_hint and beat.player_hint.strip():
            return beat.player_hint
        if beat.visibility == BeatVisibility.SECRET:
            return _HIDDEN_BEAT_TITLE
        return _DEFAULT_BEAT_TITLE

    def _handle_complete(self, rest: str) -> None:
        """Parse ``complete <story-id>`` and dispatch CompleteStoryAction."""
        from actions.definitions.gm_stories import CompleteStoryAction  # noqa: PLC0415

        story_id = self._require_arg(rest, _COMPLETE_USAGE)
        story = resolve_story_or_error(story_id)
        self._run_action(CompleteStoryAction, story_id=str(story.pk))

    def _handle_resolve(self, rest: str) -> None:
        """Parse ``resolve <episode-id> [transition-id] [notes]`` and dispatch ResolveEpisodeAction.

        ``Transition`` has no name/title field, so it can only be supplied by
        numeric pk; any non-numeric second token is treated as the start of GM
        notes.
        """
        from actions.definitions.gm_stories import ResolveEpisodeAction  # noqa: PLC0415

        tokens = rest.split()
        if not tokens:
            msg = _RESOLVE_USAGE
            raise CommandError(msg)

        episode = resolve_episode_or_error(tokens[0])
        kwargs: dict[str, object] = {"episode_id": str(episode.pk)}
        remaining = tokens[1:]

        if remaining and remaining[0].isdigit():
            kwargs["chosen_transition_id"] = remaining[0]
            remaining = remaining[1:]

        gm_notes = " ".join(remaining).strip()
        if gm_notes:
            kwargs["gm_notes"] = gm_notes

        self._run_action(ResolveEpisodeAction, **kwargs)

    def _handle_promote(self, rest: str) -> None:
        """Parse ``promote <episode-id> <target>`` and dispatch PromoteEpisodeAction."""
        from actions.definitions.gm_stories import PromoteEpisodeAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_PROMOTE_TOKENS:
            msg = _PROMOTE_USAGE
            raise CommandError(msg)

        episode = resolve_episode_or_error(tokens[0])
        self._run_action(
            PromoteEpisodeAction,
            episode_id=str(episode.pk),
            target=tokens[1].lower(),
        )

    def _handle_mark(self, rest: str) -> None:
        """Parse ``mark <beat-id> <outcome> [notes]`` and dispatch MarkBeatAction."""
        from actions.definitions.gm_stories import MarkBeatAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_MARK_TOKENS:
            msg = _MARK_USAGE
            raise CommandError(msg)

        beat_id = resolve_numeric_beat_id_or_error(tokens[0])
        outcome = tokens[1].lower()
        gm_notes = " ".join(tokens[_MIN_MARK_TOKENS:]).strip()

        kwargs: dict[str, object] = {"beat_id": beat_id, "outcome": outcome}
        if gm_notes:
            kwargs["gm_notes"] = gm_notes

        self._run_action(MarkBeatAction, **kwargs)

    def _handle_signoff(self, rest: str) -> None:
        """Grant or withdraw a treasured sign-off for a beat (#1853)."""
        from world.boundaries.models import TreasuredSubject  # noqa: PLC0415
        from world.stories.models import Beat, TreasuredSignoff  # noqa: PLC0415
        from world.stories.services.boundaries import (  # noqa: PLC0415
            grant_treasured_signoff,
            player_pending_treasured_signoffs,
            withdraw_treasured_signoff,
        )

        usage = "Usage: story signoff <beat-id> <subject> [withdraw]."
        tokens = rest.split()
        if len(tokens) < _MIN_SIGNOFF_TOKENS:
            raise CommandError(usage)

        beat_id = resolve_numeric_beat_id_or_error(tokens[0])
        try:
            beat = Beat.objects.get(pk=beat_id)
        except Beat.DoesNotExist as exc:
            msg = "No beat with that ID exists."
            raise CommandError(msg) from exc

        remaining = tokens[1:]
        withdraw = bool(remaining) and remaining[-1].lower() == _WITHDRAW_KEYWORD
        if withdraw:
            remaining = remaining[:-1]
        subject_token = " ".join(remaining).strip()
        if not subject_token:
            raise CommandError(usage)

        account = self.caller.account
        player_data = account.player_data if account else None
        if player_data is None:
            msg = "You have no player identity to sign off with."
            raise CommandError(msg)

        if withdraw:
            active_signoffs = TreasuredSignoff.objects.filter(
                beat=beat, player_data=player_data, withdrawn_at__isnull=True
            ).select_related("treasured_subject")
            signoff = self._match_subject_token(
                subject_token, [(s.treasured_subject, s) for s in active_signoffs]
            )
            if signoff is None:
                msg = f"No active sign-off for '{subject_token}' on beat {beat.pk}."
                raise CommandError(msg)
            withdraw_treasured_signoff(signoff)
            self.msg(f"Withdrawn: {signoff.treasured_subject.subject_label} on beat {beat.pk}.")
            return

        entries = player_pending_treasured_signoffs(player_data, [beat])
        pending_ids: tuple[int, ...] = entries[0].treasured_subject_ids if entries else ()
        candidates = list(TreasuredSubject.objects.filter(pk__in=pending_ids))
        subject = self._match_subject_token(subject_token, [(s, s) for s in candidates])
        if subject is None:
            msg = f"No pending sign-off for '{subject_token}' on beat {beat.pk}."
            raise CommandError(msg)
        grant_treasured_signoff(beat, player_data, subject)
        self.msg(f"Signed off: {subject.subject_label} on beat {beat.pk}.")

    # -- protect (#2001 Task 7) ------------------------------------------------

    def _handle_protect(self, rest: str) -> None:
        """Route ``protect <story-id> add|remove|list ...`` (GM-authored custody, #2001).

        Gated on the story's Lead GM or staff — mirrors
        ``IsProtectedSubjectStoryOwnerOrStaff``/``user_owns_or_leads_story`` exactly
        so telnet can't escalate past the web API.
        """
        from world.stories.permissions import user_owns_or_leads_story  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_PROTECT_USAGE)
        story = resolve_story_or_error(tokens[0])

        account = self.caller.account
        is_staff = bool(account and account.is_staff)
        if not is_staff and not user_owns_or_leads_story(account, story):
            msg = "You do not own or lead this story."
            raise CommandError(msg)

        sub_rest = tokens[1].strip() if len(tokens) > 1 else ""
        sub_tokens = sub_rest.split(maxsplit=1)
        if not sub_tokens:
            raise CommandError(_PROTECT_USAGE)
        subverb = sub_tokens[0].lower()
        tail = sub_tokens[1].strip() if len(sub_tokens) > 1 else ""

        if subverb == "add":  # noqa: STRING_LITERAL
            self._handle_protect_add(story, tail)
        elif subverb == "remove":  # noqa: STRING_LITERAL
            self._handle_protect_remove(story, tail)
        elif subverb == "list":  # noqa: STRING_LITERAL
            self._handle_protect_list(story)
        else:
            raise CommandError(_PROTECT_USAGE)

    def _handle_protect_add(self, story: Story, tail: str) -> None:
        """Parse ``add <kind>=<subject-ref> [beat=<id>] [notes=<text>]`` and create
        a ``StoryProtectedSubject`` row — plain ORM, mirroring
        ``StoryProtectedSubjectSerializer``'s exactly-one-subject rule (enforced here
        by construction: ``_resolve_subject_ref`` populates exactly one typed field)."""
        from world.stories.models import Beat, StoryProtectedSubject  # noqa: PLC0415

        if not tail:
            raise CommandError(_PROTECT_USAGE)
        kwargs, _flags = parse_kv_and_flags(
            tail, multiword_keys=_PROTECT_ADD_MULTIWORD_KEYS, known_flags=frozenset()
        )

        kind_key = self._require_single_subject_kind_key(kwargs)
        subject_ref = kwargs[kind_key].strip()
        if not subject_ref:
            msg = f"{kind_key}=<subject-ref> may not be blank."
            raise CommandError(msg)
        subject_kind, typed_fields = self._resolve_subject_ref(kind_key, subject_ref)

        beat = None
        beat_token = kwargs.get("beat", "").strip()
        if beat_token:
            beat_id = resolve_numeric_beat_id_or_error(beat_token)
            try:
                beat = Beat.objects.get(pk=beat_id)
            except Beat.DoesNotExist as exc:
                msg = "No beat with that ID exists."
                raise CommandError(msg) from exc
            if beat.episode.chapter.story_id != story.pk:
                msg = "That beat does not belong to this story."
                raise CommandError(msg)

        notes = kwargs.get("notes", "").strip()

        protected = StoryProtectedSubject.objects.create(
            story=story,
            subject_kind=subject_kind,
            beat=beat,
            notes=notes,
            **typed_fields,
        )
        self.msg(
            f"Protected #{protected.pk}: {self._protect_label(protected)} "
            f"({protected.get_subject_kind_display()})."
        )

    def _handle_protect_remove(self, story: Story, tail: str) -> None:
        """Parse ``remove <protected-id>`` and deactivate the protection.

        Soft (``is_active=False``), never a hard delete — a ``StoryProtectedSubject``
        row is story-significant data (its ``CustodyClearance`` decision trail CASCADEs
        from it), mirroring the never-hard-delete-story-significant-data rule
        ``revoke_clearance`` follows for clearances themselves.
        """
        from world.stories.models import StoryProtectedSubject  # noqa: PLC0415

        protected_id = self._require_arg(tail, _PROTECT_USAGE)
        if not protected_id.isdigit():
            msg = "The protected-subject ID must be numeric."
            raise CommandError(msg)
        try:
            protected = StoryProtectedSubject.objects.get(pk=protected_id, story=story)
        except StoryProtectedSubject.DoesNotExist as exc:
            msg = "No protected subject with that ID exists for this story."
            raise CommandError(msg) from exc
        protected.is_active = False
        protected.save(update_fields=["is_active"])
        self.msg(f"Deactivated protection #{protected.pk} ({self._protect_label(protected)}).")

    def _handle_protect_list(self, story: Story) -> None:
        """List every ``StoryProtectedSubject`` (active and inactive) for *story*."""
        from world.stories.models import StoryProtectedSubject  # noqa: PLC0415

        protections = StoryProtectedSubject.objects.filter(story=story).order_by(
            "-created_at", "-pk"
        )
        if not protections:
            self.msg(f"No protected subjects for story #{story.pk}.")
            return
        lines = [f"Protected subjects for {story.title} (#{story.pk}):"]
        for protected in protections:
            active = "active" if protected.is_active else "inactive"
            beat_bit = f" beat=#{protected.beat_id}" if protected.beat_id else ""
            lines.append(
                f"  [{protected.pk}] {protected.get_subject_kind_display()}: "
                f"{self._protect_label(protected)}{beat_bit} ({active})"
            )
        self.msg("\n".join(lines))

    # -- clearance (#2001 Task 7) -----------------------------------------------

    def _handle_clearance(self, rest: str) -> None:
        """Route ``clearance request|grant|deny|escalate|resolve|revoke|list ...``."""
        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_CLEARANCE_USAGE)
        subverb = tokens[0].lower()
        tail = tokens[1].strip() if len(tokens) > 1 else ""

        handlers = {
            "request": self._handle_clearance_request,
            "grant": self._handle_clearance_grant,
            "deny": self._handle_clearance_deny,
            "escalate": self._handle_clearance_escalate,
            "resolve": self._handle_clearance_resolve,
            "revoke": self._handle_clearance_revoke,
            "list": self._handle_clearance_list,
        }
        handler = handlers.get(subverb)
        if handler is None:
            raise CommandError(_CLEARANCE_USAGE)
        handler(tail)

    def _handle_clearance_request(self, tail: str) -> None:
        """Parse ``request <kind>=<subject-ref>|protected=<id> scope=<...>
        [story=<id>] [message=<text>]`` — identity-based fan-out (Task 6 review Fix
        4) or the raw pk variant for a custodian-relayed id. Mirrors
        ``CustodyClearanceRequestSerializer`` exactly: any authenticated GM may
        request clearance for any active protected subject (deliberately
        cross-story); a live (PENDING/ESCALATED) duplicate at the same scope is
        skipped (identity path, reported back) or a hard error (pk path).
        """
        if not tail:
            raise CommandError(_CLEARANCE_USAGE)

        account = self.caller.account
        gm_profile = self._require_gm_profile(account)

        kwargs, _flags = parse_kv_and_flags(
            tail, multiword_keys=_CLEARANCE_REQUEST_MULTIWORD_KEYS, known_flags=frozenset()
        )

        scope = self._require_clearance_scope(kwargs)
        requesting_story = self._resolve_requesting_story(kwargs)
        message = kwargs.get("message", "").strip()
        protections, is_pk_path = self._resolve_request_protections(kwargs)

        created, skipped = self._create_missing_clearances(
            protections,
            gm_profile=gm_profile,
            scope=scope,
            requesting_story=requesting_story,
            message=message,
            is_pk_path=is_pk_path,
        )
        self._report_clearance_request(created, skipped, scope)

    def _require_clearance_scope(self, kwargs: dict[str, str]) -> str:
        from world.stories.constants import CustodyScope  # noqa: PLC0415

        scope = kwargs.get("scope", "").strip().lower()
        if scope not in CustodyScope.values:
            msg = "scope is required and must be one of: appear, harm, remove."
            raise CommandError(msg)
        return scope

    def _resolve_requesting_story(self, kwargs: dict[str, str]) -> Story | None:
        from world.stories.models import Story  # noqa: PLC0415

        story_token = kwargs.get("story", "").strip()
        if not story_token:
            return None
        if not story_token.isdigit():
            msg = "story=<id> must be numeric."
            raise CommandError(msg)
        try:
            return Story.objects.get(pk=story_token)
        except Story.DoesNotExist as exc:
            msg = "No story with that ID exists."
            raise CommandError(msg) from exc

    def _resolve_request_protections(
        self, kwargs: dict[str, str]
    ) -> tuple[list[StoryProtectedSubject], bool]:
        """Resolve the ``protected=<id>`` pk path, or the ``<kind>=<subject-ref>``
        identity path (fanning out to every active protection sharing that
        identity, Task 6 review Fix 4). Returns (protections, is_pk_path)."""
        from world.stories.models import StoryProtectedSubject  # noqa: PLC0415
        from world.stories.services.boundaries import _subject_identity  # noqa: PLC0415
        from world.stories.services.custody_clearance import (  # noqa: PLC0415
            matching_active_protected_subjects,
        )

        protected_token = kwargs.get("protected", "").strip()
        kind_keys_present = [key for key in kwargs if key in _SUBJECT_KIND_KEYS]

        if bool(protected_token) == bool(kind_keys_present):
            msg = (
                "Provide exactly one of protected=<id>, or a subject kind "
                "(npc_fate/personal_jeopardy/item/faction/location/custom)=<subject-ref>."
            )
            raise CommandError(msg)

        if protected_token:
            if not protected_token.isdigit():
                msg = "protected=<id> must be numeric."
                raise CommandError(msg)
            try:
                protection = StoryProtectedSubject.objects.get(pk=protected_token, is_active=True)
            except StoryProtectedSubject.DoesNotExist as exc:
                msg = "No active protected subject with that ID exists."
                raise CommandError(msg) from exc
            return [protection], True

        kind_key = kind_keys_present[0]
        subject_ref = kwargs[kind_key].strip()
        if not subject_ref:
            msg = f"{kind_key}=<subject-ref> may not be blank."
            raise CommandError(msg)
        subject_kind, typed_fields = self._resolve_subject_ref(kind_key, subject_ref)
        sheet = typed_fields.get("subject_sheet")
        item = typed_fields.get("subject_item")
        society = typed_fields.get("subject_society")
        organization = typed_fields.get("subject_organization")
        identity = _subject_identity(
            subject_kind,
            sheet.pk if sheet is not None else None,
            item.pk if item is not None else None,
            society.pk if society is not None else None,
            organization.pk if organization is not None else None,
            str(typed_fields.get("subject_label", "")),
        )
        protections = matching_active_protected_subjects(identity)
        if not protections:
            msg = "No active protected subject matches that identity."
            raise CommandError(msg)
        return protections, False

    def _create_missing_clearances(  # noqa: PLR0913 — one arg per request_clearance() field
        self,
        protections: list[StoryProtectedSubject],
        *,
        gm_profile: GMProfile,
        scope: str,
        requesting_story: Story | None,
        message: str,
        is_pk_path: bool,
    ) -> tuple[list[CustodyClearance], int]:
        """Create a PENDING ``CustodyClearance`` for each of *protections* not
        already carrying a live (PENDING/ESCALATED) request from *gm_profile* at
        *scope* — skipped on the identity path, a hard error on the pk path
        (mirrors ``CustodyClearanceRequestSerializer`` exactly)."""
        from world.stories.constants import CustodyClearanceStatus  # noqa: PLC0415
        from world.stories.models import CustodyClearance  # noqa: PLC0415
        from world.stories.services.custody_clearance import request_clearance  # noqa: PLC0415

        already_pending_ids = set(
            CustodyClearance.objects.filter(
                protected_subject_id__in=[protection.pk for protection in protections],
                requested_by=gm_profile,
                scope=scope,
                status__in=(CustodyClearanceStatus.PENDING, CustodyClearanceStatus.ESCALATED),
            ).values_list("protected_subject_id", flat=True)
        )

        if is_pk_path and protections[0].pk in already_pending_ids:
            msg = "You already have a live clearance request for this subject at this scope."
            raise CommandError(msg)

        created: list[CustodyClearance] = []
        skipped = 0
        for protection in protections:
            if protection.pk in already_pending_ids:
                skipped += 1
                continue
            clearance = request_clearance(
                protected_subject=protection,
                requested_by=gm_profile,
                scope=scope,
                requesting_story=requesting_story,
                message=message,
            )
            created.append(clearance)
        return created, skipped

    def _report_clearance_request(
        self, created: list[CustodyClearance], skipped: int, scope: str
    ) -> None:
        from world.stories.services.custody_clearance import subject_display_label  # noqa: PLC0415

        if not created:
            msg = (
                "You already have a live clearance request for every matching "
                "subject at this scope."
            )
            self.msg(msg)
            return

        lines = [f"Requested {scope} clearance ({len(created)} new):"]
        lines += [f"  [{c.pk}] {subject_display_label(c.protected_subject)}" for c in created]
        if skipped:
            lines.append(f"  ({skipped} already had a live request, skipped)")
        self.msg("\n".join(lines))

    def _handle_clearance_grant(self, tail: str) -> None:
        self._decide_clearance(tail, grant=True)

    def _handle_clearance_deny(self, tail: str) -> None:
        self._decide_clearance(tail, grant=False)

    def _decide_clearance(self, tail: str, *, grant: bool) -> None:
        """Parse ``grant|deny <id> [note=<text>]``. Custodian Lead GM only — no
        staff bypass (staff act only through escalate -> resolve).

        Authority is pre-checked here with the exact ``IsClearanceCustodianGM``
        wording rather than left to ``grant_clearance``/``deny_clearance``'s own
        ``_require_custodian_gm`` guard, which is a programmer-error backstop
        only (its ``CustodyClearanceAuthorityError.user_message`` is the generic
        safe string, not this specific one) — the API reaches the same specific
        wording via its permission class instead of the service's exception.
        """
        from world.stories.exceptions import CustodyClearanceStateError  # noqa: PLC0415
        from world.stories.services.custody_clearance import (  # noqa: PLC0415
            deny_clearance,
            grant_clearance,
        )

        tokens = tail.split(maxsplit=1)
        if not tokens or not tokens[0].isdigit():
            raise CommandError(_GRANT_DENY_USAGE)
        clearance = self._get_clearance_or_error(tokens[0])

        account = self.caller.account
        gm_profile = self._require_gm_profile(account)
        self._require_custodian_gm_authority(clearance, gm_profile)

        rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            rest, multiword_keys=frozenset({"note"}), known_flags=frozenset()
        )
        note = kwargs.get("note", "").strip()

        try:
            if grant:
                updated = grant_clearance(clearance, granted_by=gm_profile, response_note=note)
            else:
                updated = deny_clearance(clearance, denied_by=gm_profile, response_note=note)
        except CustodyClearanceStateError as exc:
            raise CommandError(exc.user_message) from exc

        verb = "Granted" if grant else "Denied"
        self.msg(f"{verb} clearance #{updated.pk} ({updated.scope}).")

    def _require_custodian_gm_authority(
        self, clearance: CustodyClearance, gm_profile: GMProfile
    ) -> None:
        """Raise unless *gm_profile* is the exact custodian GM of *clearance*'s
        protected subject. Mirrors ``IsClearanceCustodianGM.has_object_permission``
        (and its ``.message``) exactly — deliberately no staff bypass."""
        table = clearance.protected_subject.story.primary_table
        if table is None or table.gm_id != gm_profile.pk:
            msg = "Only the protecting story's Lead GM may decide this clearance."
            raise CommandError(msg)

    def _handle_clearance_escalate(self, tail: str) -> None:
        """Parse ``escalate <id>``. Requester-only — the service takes no actor
        parameter, so this permission check IS the entire authorization boundary,
        mirroring ``IsClearanceRequesterGM``. Eligibility (DENIED, or PENDING and
        stale) is enforced by ``escalate_clearance`` itself."""
        from world.stories.exceptions import CustodyClearanceStateError  # noqa: PLC0415
        from world.stories.services.custody_clearance import escalate_clearance  # noqa: PLC0415

        token = self._require_arg(tail, _ESCALATE_USAGE)
        if not token.isdigit():
            raise CommandError(_ESCALATE_USAGE)
        clearance = self._get_clearance_or_error(token)

        account = self.caller.account
        gm_profile = self._require_gm_profile(account)
        if clearance.requested_by_id != gm_profile.pk:
            msg = "Only the requesting GM may escalate this clearance."
            raise CommandError(msg)

        try:
            updated = escalate_clearance(clearance)
        except CustodyClearanceStateError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"Escalated clearance #{updated.pk} to staff review.")

    def _handle_clearance_resolve(self, tail: str) -> None:
        """Parse ``resolve <id> grant|deny [note=<text>]``. Staff-only — no GM
        bypass ever, mirroring ``IsStaffForCustodyResolution``."""
        from world.stories.exceptions import (  # noqa: PLC0415
            CustodyClearanceAuthorityError,
            CustodyClearanceStateError,
        )
        from world.stories.services.custody_clearance import resolve_escalation  # noqa: PLC0415

        account = self.caller.account
        if not (account and account.is_staff):
            msg = "Only staff may resolve an escalated custody clearance."
            raise CommandError(msg)

        tokens = tail.split(maxsplit=2)
        if (
            len(tokens) < _MIN_RESOLVE_TOKENS
            or not tokens[0].isdigit()
            or tokens[1].lower() not in ("grant", "deny")
        ):
            raise CommandError(_RESOLVE_CLEARANCE_USAGE)
        clearance = self._get_clearance_or_error(tokens[0])
        grant = tokens[1].lower() == "grant"  # noqa: STRING_LITERAL

        rest = tokens[_MIN_RESOLVE_TOKENS] if len(tokens) > _MIN_RESOLVE_TOKENS else ""
        kwargs, _flags = parse_kv_and_flags(
            rest, multiword_keys=frozenset({"note"}), known_flags=frozenset()
        )
        note = kwargs.get("note", "").strip()

        try:
            updated = resolve_escalation(
                clearance, staff_account=account, grant=grant, response_note=note
            )
        except (CustodyClearanceStateError, CustodyClearanceAuthorityError) as exc:
            raise CommandError(exc.user_message) from exc
        verb = "Granted" if grant else "Denied"
        self.msg(f"{verb} (staff) clearance #{updated.pk} ({updated.scope}).")

    def _handle_clearance_revoke(self, tail: str) -> None:
        """Parse ``revoke <id>``. Custodian GM's account, or staff — the one
        lifecycle action where staff stands in for the custodian directly.
        Authority is pre-checked with the exact ``IsClearanceCustodianOrStaff``
        wording (see ``_decide_clearance``'s docstring for why)."""
        from world.stories.exceptions import CustodyClearanceStateError  # noqa: PLC0415
        from world.stories.services.custody_clearance import revoke_clearance  # noqa: PLC0415

        token = self._require_arg(tail, _REVOKE_USAGE)
        if not token.isdigit():
            raise CommandError(_REVOKE_USAGE)
        clearance = self._get_clearance_or_error(token)

        account = self.caller.account
        self._require_custodian_or_staff_authority(clearance, account)
        try:
            revoke_clearance(clearance, revoked_by=account)
        except CustodyClearanceStateError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"Revoked clearance #{clearance.pk}.")

    def _require_custodian_or_staff_authority(
        self, clearance: CustodyClearance, account: AccountDB | None
    ) -> None:
        """Raise unless *account* is staff, or the custodian GM's account.
        Mirrors ``IsClearanceCustodianOrStaff`` (and its ``.message``) exactly."""
        from world.gm.models import GMProfile  # noqa: PLC0415

        if account is not None and account.is_staff:
            return
        gm_profile = None
        try:
            gm_profile = account.gm_profile if account is not None else None
        except GMProfile.DoesNotExist:
            gm_profile = None
        table = clearance.protected_subject.story.primary_table
        if gm_profile is None or table is None or table.gm_id != gm_profile.pk:
            msg = "Only the protecting story's Lead GM or staff may revoke this clearance."
            raise CommandError(msg)

    def _handle_clearance_list(self, tail: str) -> None:
        """``list [pending]`` — the caller's own requests + requests targeting
        stories they own/lead; staff sees all. Mirrors
        ``CustodyClearanceViewSet.get_queryset`` exactly."""
        from django.db.models import Q  # noqa: PLC0415

        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.stories.constants import CustodyClearanceStatus  # noqa: PLC0415
        from world.stories.models import CustodyClearance  # noqa: PLC0415
        from world.stories.services.custody_clearance import subject_display_label  # noqa: PLC0415

        account = self.caller.account
        is_staff = bool(account and account.is_staff)
        qs = CustodyClearance.objects.select_related(
            "protected_subject__story__primary_table__gm__account",
            "requested_by__account",
        )
        if not is_staff:
            gm_profile = None
            try:
                gm_profile = account.gm_profile if account else None
            except GMProfile.DoesNotExist:
                gm_profile = None
            filters_q = Q(protected_subject__story__owners=account) if account else Q(pk__in=[])
            if gm_profile is not None:
                filters_q |= Q(requested_by=gm_profile)
                filters_q |= Q(protected_subject__story__primary_table__gm=gm_profile)
            qs = qs.filter(filters_q).distinct()

        if tail.strip().lower() == "pending":  # noqa: STRING_LITERAL
            qs = qs.filter(status=CustodyClearanceStatus.PENDING)

        clearances = list(qs.order_by("-created_at", "-pk"))
        if not clearances:
            self.msg("No custody clearances to show.")
            return
        lines = ["Custody clearances:"]
        for clearance in clearances:
            label = subject_display_label(clearance.protected_subject)
            lines.append(
                f"  [{clearance.pk}] {clearance.scope} — {label} — {clearance.status}"
                f" (requested by {clearance.requested_by.account.username})"
            )
        self.msg("\n".join(lines))

    # -- crossover (#2002) ------------------------------------------------------

    def _handle_crossover(self, rest: str) -> None:
        """Route ``crossover invite|accept|decline|withdraw|list ...`` (#2002).

        Thin over ``world.stories.services.crossover`` — the same services the
        ``CrossoverInviteViewSet`` calls. Authorization replicated inline to
        match the API's permission classes exactly (sender-only withdraw,
        recipient-only accept/decline) so telnet cannot escalate.
        """
        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_CROSSOVER_USAGE)
        subverb = tokens[0].lower()
        tail = tokens[1].strip() if len(tokens) > 1 else ""

        handlers = {
            "invite": self._handle_crossover_invite,
            "accept": self._handle_crossover_accept,
            "decline": self._handle_crossover_decline,
            "withdraw": self._handle_crossover_withdraw,
            "list": self._handle_crossover_list,
        }
        handler = handlers.get(subverb)
        if handler is None:
            raise CommandError(_CROSSOVER_USAGE)
        handler(tail)

    def _handle_crossover_invite(self, tail: str) -> None:
        """Parse ``invite <event-id> story=<id> [episode=<id>] [message=<text>]``."""
        from world.events.models import Event  # noqa: PLC0415
        from world.stories.models import Episode, Story  # noqa: PLC0415

        if not tail:
            raise CommandError(_CROSSOVER_INVITE_USAGE)
        parts = tail.split(maxsplit=1)
        event_token = parts[0].strip()
        kv_tail = parts[1].strip() if len(parts) > 1 else ""
        if not event_token.isdigit():
            raise CommandError(_CROSSOVER_INVITE_USAGE)

        account = self.caller.account
        gm_profile = self._require_gm_profile(account)

        kwargs, _flags = parse_kv_and_flags(
            kv_tail, multiword_keys=_CROSSOVER_MULTIWORD_KEYS, known_flags=frozenset()
        )
        story_token = kwargs.get("story", "").strip()
        episode_token = kwargs.get("episode", "").strip()
        message = kwargs.get("message", "").strip()
        if not story_token.isdigit():
            raise CommandError(_CROSSOVER_INVITE_USAGE)

        try:
            event = Event.objects.get(pk=int(event_token))
        except Event.DoesNotExist as exc:
            msg = "No event with that ID exists."
            raise CommandError(msg) from exc
        try:
            story = Story.objects.get(pk=int(story_token))
        except Story.DoesNotExist as exc:
            msg = "No story with that ID exists."
            raise CommandError(msg) from exc
        proposed_episode = None
        if episode_token:
            if not episode_token.isdigit():
                msg = "episode must be a numeric ID."
                raise CommandError(msg)
            try:
                proposed_episode = Episode.objects.get(pk=int(episode_token))
            except Episode.DoesNotExist as exc:
                msg = "No episode with that ID exists."
                raise CommandError(msg) from exc

        from world.stories.exceptions import CrossoverError  # noqa: PLC0415
        from world.stories.services.crossover import create_crossover_invite  # noqa: PLC0415

        try:
            invite = create_crossover_invite(
                from_gm=gm_profile,
                event=event,
                to_story=story,
                proposed_episode=proposed_episode,
                message=message,
            )
        except CrossoverError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(
            f"Crossover invite #{invite.pk} sent: {story.title} invited to event"
            f' "{event.name}" (status: pending).'
        )

    def _handle_crossover_accept(self, tail: str) -> None:
        """Parse ``accept <invite-id> [episode=<id>] [note=<text>]``."""
        if not tail:
            raise CommandError(_CROSSOVER_USAGE)
        parts = tail.split(maxsplit=1)
        invite_token = parts[0].strip()
        kv_tail = parts[1].strip() if len(parts) > 1 else ""
        if not invite_token.isdigit():
            raise CommandError(_CROSSOVER_USAGE)

        invite = self._get_crossover_or_error(int(invite_token))
        kwargs, _flags = parse_kv_and_flags(
            kv_tail, multiword_keys=_CROSSOVER_MULTIWORD_KEYS, known_flags=frozenset()
        )
        episode_token = kwargs.get("episode", "").strip()
        note = kwargs.get("note", "").strip()

        from world.stories.models import Episode  # noqa: PLC0415

        accepted_episode = None
        if episode_token:
            if not episode_token.isdigit():
                msg = "episode must be a numeric ID."
                raise CommandError(msg)
            try:
                accepted_episode = Episode.objects.get(pk=int(episode_token))
            except Episode.DoesNotExist as exc:
                msg = "No episode with that ID exists."
                raise CommandError(msg) from exc

        from world.stories.exceptions import CrossoverError  # noqa: PLC0415
        from world.stories.services.crossover import accept_crossover_invite  # noqa: PLC0415

        try:
            updated = accept_crossover_invite(
                invite=invite,
                accepting_account=self.caller.account,
                accepted_episode=accepted_episode,
                response_note=note,
            )
        except CrossoverError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(
            f"Crossover invite #{updated.pk} accepted: {updated.to_story.title}"
            " linked to the shared event."
        )

    def _handle_crossover_decline(self, tail: str) -> None:
        """Parse ``decline <invite-id> [note=<text>]``."""
        if not tail:
            raise CommandError(_CROSSOVER_USAGE)
        parts = tail.split(maxsplit=1)
        invite_token = parts[0].strip()
        kv_tail = parts[1].strip() if len(parts) > 1 else ""
        if not invite_token.isdigit():
            raise CommandError(_CROSSOVER_USAGE)

        invite = self._get_crossover_or_error(int(invite_token))
        kwargs, _flags = parse_kv_and_flags(
            kv_tail, multiword_keys=_CROSSOVER_MULTIWORD_KEYS, known_flags=frozenset()
        )
        note = kwargs.get("note", "").strip()

        from world.stories.exceptions import CrossoverError  # noqa: PLC0415
        from world.stories.services.crossover import decline_crossover_invite  # noqa: PLC0415

        try:
            updated = decline_crossover_invite(
                invite=invite,
                responding_account=self.caller.account,
                response_note=note,
            )
        except CrossoverError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"Crossover invite #{updated.pk} declined.")

    def _handle_crossover_withdraw(self, tail: str) -> None:
        """Parse ``withdraw <invite-id>``."""
        if not tail or not tail.strip().isdigit():
            raise CommandError(_CROSSOVER_USAGE)
        invite = self._get_crossover_or_error(int(tail.strip()))

        from world.stories.exceptions import CrossoverError  # noqa: PLC0415
        from world.stories.services.crossover import withdraw_crossover_invite  # noqa: PLC0415

        try:
            updated = withdraw_crossover_invite(
                invite=invite,
                withdrawing_account=self.caller.account,
            )
        except CrossoverError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"Crossover invite #{updated.pk} withdrawn.")

    def _handle_crossover_list(self, tail: str) -> None:
        """List the caller's sent + received crossover invites."""
        from django.db.models import Q  # noqa: PLC0415

        from world.stories.constants import CrossoverInviteStatus  # noqa: PLC0415
        from world.stories.models import CrossoverInvite  # noqa: PLC0415

        account = self.caller.account
        if account is None:
            raise CommandError(_NEEDS_GM_PROFILE)
        qs = CrossoverInvite.objects.filter(
            Q(from_gm__account=account) | Q(to_story__owners=account)
        ).distinct()
        if tail.strip().lower() == "pending":  # noqa: STRING_LITERAL
            qs = qs.filter(status=CrossoverInviteStatus.PENDING)
        qs = qs.order_by("-created_at")
        if not qs:
            self.msg("You have no crossover invites.")
            return
        lines = ["Your crossover invites:"]
        for invite in qs.select_related("event", "to_story", "from_gm__account"):
            direction = "sent" if invite.from_gm.account_id == account.pk else "received"
            lines.append(
                f"  [{invite.pk}] {direction} — {invite.to_story.title}"
                f' / event "{invite.event.name}" ({invite.status})'
            )
        self.msg("\n".join(lines))

    def _handle_impact(self, rest: str) -> None:
        """Set a story's impact tier (Lead GM; editable until cleared, #2003).

        ``story impact <story-id>=<table|regional|world>``. Gated on the
        story's Lead GM or staff — mirrors ``user_owns_or_leads_story`` exactly
        so telnet can't escalate past the web API. Refuses to lower a tier once
        a review is CLEARED (the tier is frozen at clearance).
        """
        from world.stories.constants import ImpactTier  # noqa: PLC0415
        from world.stories.permissions import user_owns_or_leads_story  # noqa: PLC0415
        from world.stories.services.canon_review import story_is_cleared  # noqa: PLC0415

        if "=" not in rest:
            raise CommandError(_IMPACT_USAGE)
        story_part, tier_part = rest.split("=", 1)
        story = resolve_story_or_error(story_part.strip())
        tier_text = tier_part.strip().lower()

        tier_map = {
            "table": ImpactTier.TABLE,
            "regional": ImpactTier.REGIONAL,
            "world": ImpactTier.WORLD,
        }
        if tier_text not in tier_map:
            raise CommandError(_IMPACT_USAGE)
        new_tier = tier_map[tier_text]

        account = self.caller.account
        is_staff = bool(account and account.is_staff)
        if not is_staff and not user_owns_or_leads_story(account, story):
            msg = "You do not own or lead this story."
            raise CommandError(msg)
        if story_is_cleared(story):
            msg = "This story's impact tier is frozen — it has a cleared canon review."
            raise CommandError(msg)

        story.impact_tier = new_tier
        story.save(update_fields=["impact_tier"])
        self.msg(f"Impact tier set to {new_tier} for {story.title}.")

    def _handle_review_status(self, rest: str) -> None:
        """Show a story's impact tier, review state, and readiness problems (#2003).

        ``story review-status <story-id>`` — the Lead GM's own readout.
        """
        from world.stories.constants import CanonReviewStatus  # noqa: PLC0415
        from world.stories.permissions import user_owns_or_leads_story  # noqa: PLC0415
        from world.stories.services.canon_review import (  # noqa: PLC0415
            escalation_tier_for_story,
            latest_review_for_story,
            story_is_cleared,
        )

        tokens = rest.split()
        if not tokens:
            raise CommandError(_REVIEW_STATUS_USAGE)
        story = resolve_story_or_error(tokens[0])

        account = self.caller.account
        is_staff = bool(account and account.is_staff)
        if not is_staff and not user_owns_or_leads_story(account, story):
            msg = "You do not own or lead this story."
            raise CommandError(msg)

        effective_tier = escalation_tier_for_story(story)
        review = latest_review_for_story(story)
        cleared = story_is_cleared(story)

        lines = [f"Impact tier: {story.impact_tier} (effective: {effective_tier})"]
        if cleared:
            lines.append("Canon review: CLEARED")
        elif review is not None:
            status_label = dict(CanonReviewStatus.choices).get(review.status, review.status)
            lines.append(f"Canon review: {status_label}")
            if review.notes:
                lines.append(f"  Notes: {review.notes}")
        else:
            lines.append("Canon review: none requested")
        self.msg("\n".join(lines))

    def _handle_surrender(self, rest: str) -> None:
        """GM surrenders oversight of a story (#2004).

        ``story surrender <story-id>`` — Lead GM only; clears the story's
        primary_table so it enters "seeking GM" state. Mirrors the web
        ``POST /api/stories/{id}/surrender/`` endpoint.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415
        from world.gm.services import surrender_character_story  # noqa: PLC0415
        from world.stories.permissions import user_owns_or_leads_story  # noqa: PLC0415

        tokens = rest.split()
        if not tokens:
            raise CommandError(_SURRENDER_USAGE)
        story = resolve_story_or_error(tokens[0])

        account = self.caller.account
        is_staff = bool(account and account.is_staff)
        if not is_staff and not user_owns_or_leads_story(account, story):
            msg = "You do not own or lead this story."
            raise CommandError(msg)
        try:
            gm_profile = account.gm_profile
        except GMProfile.DoesNotExist:
            msg = "You must have a GM profile to surrender a story."
            raise CommandError(msg) from None
        surrender_character_story(gm_profile, story)
        self.msg(f"Surrendered oversight of {story.title}. It is now seeking a GM.")

    def _get_crossover_or_error(self, invite_id: int) -> CrossoverInvite:
        from world.stories.models import CrossoverInvite  # noqa: PLC0415

        try:
            return CrossoverInvite.objects.select_related(
                "event", "to_story", "from_gm__account"
            ).get(pk=invite_id)
        except CrossoverInvite.DoesNotExist as exc:
            msg = "No crossover invite with that ID exists."
            raise CommandError(msg) from exc

    # -- shared custody helpers --------------------------------------------------

    def _require_gm_profile(self, account: AccountDB | None) -> GMProfile:
        """Return the caller's ``GMProfile``, or raise ``CommandError``.

        Deliberately no staff bypass — matches ``IsGMProfile``: staff without a
        GMProfile of their own cannot grant/deny/escalate/request a clearance;
        the dedicated staff doors are ``resolve``/``revoke``.
        """
        from world.gm.models import GMProfile  # noqa: PLC0415

        if account is None:
            raise CommandError(_NEEDS_GM_PROFILE)
        try:
            return account.gm_profile
        except GMProfile.DoesNotExist as exc:
            raise CommandError(_NEEDS_GM_PROFILE) from exc

    def _get_clearance_or_error(self, clearance_id: str) -> CustodyClearance:
        from world.stories.models import CustodyClearance  # noqa: PLC0415

        try:
            return CustodyClearance.objects.select_related(
                "protected_subject__story__primary_table__gm",
                "requested_by__account",
            ).get(pk=clearance_id)
        except CustodyClearance.DoesNotExist as exc:
            msg = "No custody clearance with that ID exists."
            raise CommandError(msg) from exc

    def _require_single_subject_kind_key(self, kwargs: dict[str, str]) -> str:
        kind_keys_present = [key for key in kwargs if key in _SUBJECT_KIND_KEYS]
        if len(kind_keys_present) != 1:
            msg = (
                "Provide exactly one subject kind (npc_fate/personal_jeopardy/item/"
                "faction/org/society/location/custom)=<subject-ref>. "
                "(org/society disambiguate faction when a name matches both.)"
            )
            raise CommandError(msg)
        return kind_keys_present[0]

    def _resolve_subject_ref(
        self, kind_key: str, subject_ref: str
    ) -> tuple[str, dict[str, object]]:
        """Resolve *subject_ref* (per *kind_key*) to a (subject_kind, typed-fields)
        pair — shared by ``protect add`` (builds a ``StoryProtectedSubject`` row)
        and ``clearance request``'s identity path (builds a ``SubjectIdentity``
        tuple). NPC_FATE/PERSONAL_JEOPARDY resolve a character by name (global
        search, mirrors ``grant_item.py``); ITEM by numeric id; FACTION tries an
        Organization name, then a Society name, raising a ``CommandError`` asking
        the caller to disambiguate via ``org=``/``society=`` when a name matches
        both (Task 7 review Fix 2, mirrors ``gemit.py``'s explicit-switch spirit);
        LOCATION/CUSTOM take the ref
        itself as the freeform label.
        """
        from world.items.models import ItemInstance  # noqa: PLC0415
        from world.stories.constants import StakeSubjectKind  # noqa: PLC0415

        if kind_key in ("npc_fate", "personal_jeopardy"):
            sheet = self._resolve_character_sheet_by_name(subject_ref)
            subject_kind = (
                StakeSubjectKind.NPC_FATE
                if kind_key == "npc_fate"  # noqa: STRING_LITERAL
                else StakeSubjectKind.PERSONAL_JEOPARDY
            )
            return subject_kind, {"subject_sheet": sheet}

        if kind_key == "item":  # noqa: STRING_LITERAL
            if not subject_ref.isdigit():
                msg = "item=<subject-ref> must be an item instance ID."
                raise CommandError(msg)
            try:
                item = ItemInstance.objects.get(pk=subject_ref)
            except ItemInstance.DoesNotExist as exc:
                msg = "No item instance with that ID exists."
                raise CommandError(msg) from exc
            return StakeSubjectKind.ITEM, {"subject_item": item}

        if kind_key in ("org", "society", "faction"):  # noqa: STRING_LITERAL
            return self._resolve_faction_ref(kind_key, subject_ref)

        if kind_key == "location":  # noqa: STRING_LITERAL
            return StakeSubjectKind.LOCATION, {"subject_label": subject_ref}

        # kind_key == "custom"
        return StakeSubjectKind.CUSTOM, {"subject_label": subject_ref}

    def _resolve_faction_ref(
        self, kind_key: str, subject_ref: str
    ) -> tuple[str, dict[str, object]]:
        """Resolve a FACTION subject-ref for ``kind_key`` in ``{"org", "society", "faction"}``.

        ``org``/``society`` are explicit disambiguating aliases (Task 7 review Fix
        2): the caller names which kind of faction they mean, so only that lookup
        runs. Plain ``faction`` tries both and raises a ``CommandError`` asking the
        caller to pick ``org=``/``society=`` when a name matches both — mirrors
        ``gemit.py``'s explicit-switch spirit.
        """
        from world.stories.constants import StakeSubjectKind  # noqa: PLC0415

        organization = (
            None
            if kind_key == "society"  # noqa: STRING_LITERAL
            else self._resolve_organization_by_name(subject_ref)
        )
        society = (
            None
            if kind_key == "org"  # noqa: STRING_LITERAL
            else self._resolve_society_by_name(subject_ref)
        )

        if kind_key == "org":  # noqa: STRING_LITERAL
            if organization is None:
                msg = f"No organization named '{subject_ref}'."
                raise CommandError(msg)
            return StakeSubjectKind.FACTION, {"subject_organization": organization}

        if kind_key == "society":  # noqa: STRING_LITERAL
            if society is None:
                msg = f"No society named '{subject_ref}'."
                raise CommandError(msg)
            return StakeSubjectKind.FACTION, {"subject_society": society}

        # kind_key == "faction"
        if organization is not None and society is not None:
            msg = (
                f"'{subject_ref}' matches both an organization and a society — "
                "specify org=<name> or society=<name>."
            )
            raise CommandError(msg)
        if organization is not None:
            return StakeSubjectKind.FACTION, {"subject_organization": organization}
        if society is not None:
            return StakeSubjectKind.FACTION, {"subject_society": society}
        msg = f"No organization or society named '{subject_ref}'."
        raise CommandError(msg)

    def _resolve_organization_by_name(self, subject_ref: str) -> Organization | None:
        from world.societies.models import Organization  # noqa: PLC0415

        return Organization.objects.filter(name__iexact=subject_ref).first()

    def _resolve_society_by_name(self, subject_ref: str) -> Society | None:
        from world.societies.models import Society  # noqa: PLC0415

        return Society.objects.filter(name__iexact=subject_ref).first()

    def _resolve_character_sheet_by_name(self, name: str) -> CharacterSheet:
        """Resolve a ``CharacterSheet`` by character name via a global search
        (mirrors ``grant_item.py``'s ``CmdGrantItem._run``), quiet so we control
        the error message and never double-message the caller."""
        matches = self.caller.search(name, global_search=True, quiet=True)
        if not matches:
            msg = f"No character found named '{name}'."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"Multiple characters match '{name}'."
            raise CommandError(msg)
        target = matches[0]
        sheet = target.character_sheet
        if sheet is None:
            msg = f"'{name}' is not a character with a sheet."
            raise CommandError(msg)
        return sheet

    def _protect_label(self, protected: StoryProtectedSubject) -> str:
        from world.stories.services.custody_clearance import subject_display_label  # noqa: PLC0415

        return subject_display_label(protected)

    @staticmethod
    def _match_subject_token(
        token: str,
        subject_and_result_pairs: list[tuple[TreasuredSubject, _SignoffMatchT]],
    ) -> _SignoffMatchT | None:
        """Match *token* (numeric pk or case-insensitive label) among the given
        (TreasuredSubject, result) pairs, returning the matching result or None."""
        if token.isdigit():
            token_id = int(token)
            for subject, result in subject_and_result_pairs:
                if subject.pk == token_id:
                    return result
            return None
        for subject, result in subject_and_result_pairs:
            if subject.subject_label.lower() == token.lower():
                return result
        return None
