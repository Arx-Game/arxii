"""Commands package - user interface layer.

Command classes should be imported from their specific modules, not from this
package directly. This prevents import cascades that trigger heavy Evennia
imports during URL loading.

Example:
    # Good - import from specific module
    from commands.door import CmdLock, CmdUnlock
    from commands.evennia_overrides.communication import CmdPose, CmdSay

    # Bad - would trigger import cascade (no longer supported)
    from commands import CmdLock, CmdPose
"""
