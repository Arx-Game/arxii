"""RIVALS consent mode decision (#2170) — pure decide_consent_block logic."""

from django.test import SimpleTestCase

from world.consent.constants import ConsentMode
from world.consent.services import decide_consent_block


def _decide(*, is_rival: bool, whitelisted: bool = False) -> bool:
    return decide_consent_block(
        ConsentMode.RIVALS,
        actor_present=True,
        whitelisted=whitelisted,
        blacklisted=False,
        is_friend=False,
        is_rival=is_rival,
    )


class RivalsModeTests(SimpleTestCase):
    def test_blocks_a_non_rival(self) -> None:
        self.assertTrue(_decide(is_rival=False))

    def test_allows_a_mutual_rival(self) -> None:
        self.assertFalse(_decide(is_rival=True))

    def test_allows_a_whitelisted_actor_even_without_rivalry(self) -> None:
        self.assertFalse(_decide(is_rival=False, whitelisted=True))

    def test_friendship_alone_does_not_pass_rivals_mode(self) -> None:
        # A friend is not a rival — RIVALS gates on rivalry (or whitelist), not friendship.
        self.assertTrue(
            decide_consent_block(
                ConsentMode.RIVALS,
                actor_present=True,
                whitelisted=False,
                blacklisted=False,
                is_friend=True,
                is_rival=False,
            )
        )

    def test_absent_actor_probe_is_blocked(self) -> None:
        self.assertTrue(
            decide_consent_block(
                ConsentMode.RIVALS,
                actor_present=False,
                whitelisted=False,
                blacklisted=False,
                is_friend=False,
                is_rival=False,
            )
        )
