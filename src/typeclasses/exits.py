"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""

from functools import cached_property

from evennia.objects.objects import DefaultExit

from commands.evennia_overrides.exit_command import CmdExit
from flows.object_states.exit_state import ExitState
from typeclasses.mixins import ObjectParent


class Exit(ObjectParent, DefaultExit):
    # flake8: noqa: B950
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property. This version uses the flow
    system for traversal instead of Evennia's default command system.

    The exit creates a flow-based command that emits traversal events
    and uses service functions for the actual movement.

    Relevant hooks to overload (compared to other types of Objects):
        at_traverse(traveller, target_loc) - called to do the actual traversal and calling of the other hooks.
                                            If overloading this, consider using super() to use the default
                                            movement implementation (and hook-calling).
        at_post_traverse(traveller, source_loc) - called by at_traverse just after traversing.
        at_failed_traverse(traveller) - called by at_traverse if traversal failed for some reason. Will
                                        not be called if the attribute `err_traverse` is
                                        defined, in which case that will simply be echoed.
    """

    state_class = ExitState
    exit_command = CmdExit

    @cached_property
    def item_data(self):
        """Exit-specific item data handler."""
        from evennia_extensions.data_handlers import ExitItemDataHandler

        return ExitItemDataHandler(self)
