"""The page command's web form descriptor.

Everything a player does with ``page`` is typed through the command handler in
``integration_tests/test_faces_silences_and_the_floor_journeys.py``
(``KeepingSomeoneOut``): delivery and the sender's own line, an unplayed
character, one off the roster, the usage line, quiet mode and the allow-list both
ways, and a blocked pair's page suppressed with the staff flag written (#3657).
What stays here is the one shape no journey reaches: the descriptor the web
composer reads to draw the page form.
"""

from django.test import TestCase

from commands.evennia_overrides.communication import CmdPage


class CmdPageDescriptorTests(TestCase):
    def test_page_exposes_usage_metadata(self):
        """CmdPage should expose usage information for the frontend."""

        cmd = CmdPage()
        payload = cmd.to_payload()
        descriptor = payload["descriptors"][0]
        assert descriptor["prompt"] == "page character=message"
        assert descriptor["params_schema"] == {
            "character": {
                "type": "string",
                "widget": "character-search",
                "options_endpoint": "/api/characters/online/",
            },
            "message": {"type": "string"},
        }
