"""Player-postable bulletin boards (#3286).

A ``Board`` is either a LOCATION board (bound to a ``RoomProfile``, riding the
Notice Board room feature) or an ORG board (bound to an ``Organization``).
``BoardPost`` rows are IC notices authored by a ``scenes.Persona`` — a masked
persona posts under its false identity. See ``docs/systems/boards.md``.
"""
