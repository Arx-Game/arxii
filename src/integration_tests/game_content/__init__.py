"""Compatibility facade — the seed cluster masters live in ``world.seeds.game_content``.

Relocated by roadmap 3.2 (#1220): these modules are seed-content builders, not
integration tests, so they moved to ``world.seeds.game_content``. This package
keeps thin per-module facades (see the sibling ``.py`` files here) so existing
``integration_tests.game_content.<module>`` imports in the test suite keep
working with zero test-file edits. New code should import from
``world.seeds.game_content`` directly.
"""
