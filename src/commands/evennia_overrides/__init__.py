"""Evennia command overrides grouped by function.

Command classes should be imported from their specific modules to prevent
import cascades that trigger heavy Evennia imports.

Example:
    from commands.evennia_overrides.builder import CmdDig, CmdLink
    from commands.evennia_overrides.movement import CmdDrop, CmdGet
    from commands.evennia_overrides.perception import CmdLook
"""

__all__: list[str] = []  # Explicit: this package exports nothing at module level
