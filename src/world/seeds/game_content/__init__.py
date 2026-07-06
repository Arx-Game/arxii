"""Seed cluster masters — the ``seed_*_dev()`` content builders for dev/test data.

Relocated from ``integration_tests.game_content`` (roadmap 3.2, #1220): these
modules author production-seedable content (magic, items, combat, battles,
challenges, characters, checks, clash, conditions, social), not integration
tests. ``integration_tests.game_content`` keeps a thin compatibility facade
so existing test imports keep working; new code should import from here.
"""
