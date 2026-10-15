"""Journeys, fuzz and cross-system integration tests for Arx II (#3657).

This package is the home of the first two of the suite's three layers:
``harness.JourneyCase`` drives a player's story through the real seams (the
command handler, ``dispatch_player_action``, the REST client); ``fuzz/`` throws
malformed input at those seams. ``pipeline/`` holds the journeys written
before the harness existed. CI runs this package on every PR (shard-2 of
``.github/workflows/ci.yml``); it is PostgreSQL-only, like every journey.
"""
