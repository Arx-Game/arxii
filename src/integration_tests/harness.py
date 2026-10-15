"""The journey harness (#3657): drive the game the way a player does.

A journey test proves a story a player or staff member lives through, on the
seams they reach it by: a typed line through the real command handler, a web
action through ``dispatch_player_action``, a REST call through ``APIClient``.
It asserts what the game told the player, not only what the database holds
(the ``running-tests`` rule: never assume player omniscience).

Why this exists: before it, every telnet "e2e" test built a ``Cmd`` by hand,
set ``caller.msg = MagicMock()`` and called ``.func()``. That skips the command
handler (cmdset membership, the switch split, ``parse``), which is how an
``ArxCommand`` that never parsed its ``/switches`` stayed green on ``main``
(#4352). ``JourneyCase.telnet`` goes through ``execute_cmd`` instead, so the
line a player types is the line the test types.

Journeys are PostgreSQL-only by construction (ruled 2026-10-15): they cross
the partitioned ``Interaction`` table and the materialized views the SQLite
tier does not build. ``@tag("postgres")`` on the base class is inherited.

    class ASayJourney(JourneyCase):
        def test_a_greeting_reaches_the_room(self):
            room = self.make_room("The Lantern")
            ysmay = self.make_player("Ysmay", room=room)
            hobb = self.make_player("Hobb", room=room)
            self.watch(hobb)
            told = self.telnet(ysmay, 'say Good evening.')
            self.assertIn('You say "Good evening."', told)
            self.assertTold(hobb, 'Ysmay says "Good evening."')
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from django.test import TestCase, tag
from evennia.utils.idmapper.models import SharedMemoryModel
from rest_framework.test import APIClient
from twisted.python.failure import Failure

from actions.constants import ActionBackend
from actions.types import ActionRef
from commands.tests.message_capture import message_text
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import DispatchResult


class Mailbox:
    """Everything ``msg`` sent to one object, as text and as the raw calls.

    Stands in for the object's ``msg`` for the life of the test (an instance
    attribute shadows the typeclass method; ``JourneyCase`` removes it again).
    ``lines`` holds the text of each call, whatever shape it came in: a bare
    string or Evennia's ``(text, {"type": kind})`` tuple. ``calls`` keeps the
    keyword frames too (``command_error={...}``), for a test that asserts one.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, text: object = None, *args: Any, **kwargs: Any) -> None:
        self.calls.append(((text, *args), kwargs))
        if text is not None:
            self.lines.append(message_text(text))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _flush_identity_map() -> None:
    """Drop every cached SharedMemoryModel instance, safe or not."""

    def leaves(classes: list[type]) -> Any:
        for cls in classes:
            subclasses = cls.__subclasses__()
            if subclasses:
                yield from leaves(subclasses)
            else:
                yield cls

    for cls in leaves([SharedMemoryModel]):
        cls.flush_instance_cache(force=True)


@tag("postgres")
class JourneyCase(TestCase):
    """Base class for journey tests. See the module docstring for the shape."""

    def setUp(self) -> None:
        super().setUp()
        self._mailboxes: dict[int, Mailbox] = {}

    def tearDown(self) -> None:
        # The rooms and characters a journey builds are rolled back with the
        # test, but Evennia's identity map keeps the instances (ADR-0008), and
        # ``ObjectDB.objects.get(id=...)`` answers from that map without a
        # query. A later test in the same process that creates an object with
        # no home resolves ``settings.DEFAULT_HOME`` ("#2") to the dead
        # instance and writes a home the database no longer holds: ten magic
        # tests died that way on PR #4360's first two CI runs. Evennia's
        # ``flush_cache()`` is not enough here: it keeps every object carrying
        # an NAttribute, and the command handler sets ``ndb.last_cmd`` on the
        # character that typed the line. So the flush is forced.
        _flush_identity_map()
        super().tearDown()

    # -- building the world ---------------------------------------------------

    @staticmethod
    def make_room(name: str = "A Quiet Room") -> ObjectDB:
        """A room of the game's own Room typeclass."""
        return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")

    @staticmethod
    def make_player(name: str, *, room: ObjectDB) -> ObjectDB:
        """A played character standing in ``room``: a sheet, a roster entry, an
        open tenure, and the tenure's account on the character, the way a
        logged-in puppet has one. ``character.db_account`` is the account."""
        character = CharacterFactory(db_key=name, location=room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        character.db_account = tenure.player_data.account
        character.save()
        return character

    @staticmethod
    def account_of(character: ObjectDB) -> AccountDB:
        """The account playing ``character`` (set by ``make_player``)."""
        return character.db_account

    # -- what the game told whom ----------------------------------------------

    def watch(self, *objects: ObjectDB) -> None:
        """Record every ``msg`` these objects receive from now on.

        ``telnet`` watches its caller on its own; call this for the onlookers
        whose lines the journey asserts (the other characters in the room).
        """
        for obj in objects:
            if obj.pk in self._mailboxes:
                continue
            box = Mailbox()
            obj.msg = box
            self._mailboxes[obj.pk] = box
            self.addCleanup(self._unwatch, obj)

    @staticmethod
    def _unwatch(obj: ObjectDB) -> None:
        # Idmapper shares the instance across tests in a class; drop the shadow.
        if "msg" in obj.__dict__:
            del obj.msg

    def mailbox(self, obj: ObjectDB) -> Mailbox:
        """The recorder for ``obj`` (watching it first if needed)."""
        self.watch(obj)
        return self._mailboxes[obj.pk]

    def said(self, obj: ObjectDB) -> str:
        """Everything the game has told ``obj`` so far in this test."""
        return self.mailbox(obj).text

    def assertTold(self, obj: ObjectDB, needle: str) -> None:  # noqa: N802 - unittest style
        """``obj`` was told a line containing ``needle``."""
        told = self.said(obj)
        if needle not in told:
            self.fail(f"{obj.key} was never told {needle!r}. Told:\n{told}")

    def assertNotTold(self, obj: ObjectDB, needle: str) -> None:  # noqa: N802
        """``obj`` was told nothing containing ``needle``."""
        told = self.said(obj)
        if needle in told:
            self.fail(f"{obj.key} was told {needle!r}. Told:\n{told}")

    # -- the seams a player reaches the game by -------------------------------

    def telnet(self, character: ObjectDB, line: str) -> str:
        """Type ``line`` as ``character`` through the real command handler.

        Returns the text the game sent ``character`` during this one command;
        ``said`` keeps the whole conversation. Cmdset membership, the alias
        match, ``parse`` and the switch split are all on the path, so a line
        that would fail a player fails here. A command that raises fails the
        test with its own exception: the handler would log the traceback and
        tell the player "there was an error", which a test must never pass.
        """
        box = self.mailbox(character)
        start = len(box.lines)
        trapped: list[BaseException] = []

        def record_error(*_args: object, **_kwargs: object) -> None:
            # Called inside the handler's ``except`` block, so the exception is live.
            exc = sys.exc_info()[1]
            if exc is not None:
                trapped.append(exc)

        with patch("evennia.commands.cmdhandler._msg_err", record_error):
            deferred = character.execute_cmd(line)
        if trapped:
            raise trapped[0]
        # The handler is a Twisted inlineCallbacks generator. With no reactor it
        # runs to the end synchronously; a failure of the handler itself lands
        # on the Deferred instead of propagating, so it is raised here.
        failures: list[Failure] = []
        deferred.addErrback(failures.append)
        if failures:
            failures[0].raiseException()
        if not deferred.called:
            self.fail(f"{line!r} did not finish synchronously (the handler yielded a wait)")
        return "\n".join(box.lines[start:])

    @staticmethod
    def web(character: ObjectDB, key: str, **kwargs: Any) -> DispatchResult:
        """Run the keyed registry action as the web client does, through
        ``dispatch_player_action`` (the seam every web action converges on)."""
        from actions.player_interface import dispatch_player_action  # noqa: PLC0415

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key=key)
        return dispatch_player_action(character, ref, dict(kwargs))

    @staticmethod
    def api(account: AccountDB | None = None) -> APIClient:
        """A REST client, signed in as ``account`` when one is given."""
        client = APIClient()
        if account is not None:
            client.force_authenticate(user=account)
        return client
