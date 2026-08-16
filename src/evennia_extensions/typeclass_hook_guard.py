"""Guard Evennia's server lifecycle hooks against bare, non-typeclassed instances.

See issue #3195.

Evennia's ``evennia/server/service.py`` ``shutdown()`` calls lifecycle hooks
(``at_server_reload``, ``at_server_shutdown``, ``unpuppet_all``, ``_pause_task``)
directly on every cached ``ObjectDB``, ``AccountDB``, and ``ScriptDB`` instance,
with no guard. Those hooks are defined on the *typeclasses*
(``DefaultObject``, ``DefaultAccount``, ``DefaultScript``), not on the bare
Django model classes. Evennia assumes every cached instance is running as its
typeclass, because ``TypedObject.__init__`` calls ``set_class_from_typeclass``
on creation. That assumption can be wrong: ``set_class_from_typeclass``
(``evennia/typeclasses/models.py``, around lines 267 to 300) has a fallback
ladder that can leave an instance bare. One branch of that ladder assigns
``__dbclass__`` instead of ``__class__``, so the instance never actually
becomes its typeclass.

On production this crashed reload outright::

    builtins.AttributeError: 'AccountDB' object has no attribute 'at_server_reload'

The exception kills the shutdown Deferred. The Server never finishes its half
of the reload handshake. ``evennia reload`` then blocks on the AMP socket
until systemd kills it at the 90 second timeout, and every deploy needs a
full restart, which disconnects players.

How a bare instance enters the idmapper cache is a separate, unresolved
question (tracked in issue #3195). This module does not address that
question. It only makes sure a missing hook cannot crash the Server.

Upstream bug found while diagnosing (not patched here; report to Evennia):
``evennia/accounts/models.py:109`` sets, on ``AccountDB``::

    __settingsclasspath__ = settings.BASE_SCRIPT_TYPECLASS

That is the Script typeclass path, not ``BASE_ACCOUNT_TYPECLASS``. An account
whose typeclass import fails and falls through to ``__settingsclasspath__``
therefore falls back to the wrong typeclass family.

Design
------
``install_lifecycle_hook_guards()`` patches the three bare model classes
(``evennia.accounts.models.AccountDB``, ``evennia.objects.models.ObjectDB``,
``evennia.scripts.models.ScriptDB``) so each carries a working no-op for
every hook the shutdown path calls, but only for hooks genuinely missing
from the bare class. A typeclass (e.g.
``typeclasses.accounts.Account``, via ``DefaultAccount``) defines its own
``at_server_reload`` closer in the MRO, so a typeclassed instance keeps using
its real hook untouched; the guard is invisible to it. Only a bare instance,
which has no such override, falls through to the guard's no-op.

The no-op is not silent. A bare instance means that object is not running as
its typeclass anywhere, so every custom hook and method defined on its real
typeclass is silently absent for it too. That is a bigger correctness problem
than the reload crash. Each time a stub actually fires, it logs a warning
naming the class and the instance pk, so the underlying condition stays
visible in the logs instead of being permanently hidden by the guard.

``ScriptDB.is_active`` is not guarded here. It is not a typeclass hook: the
idmapper metaclass (``evennia.utils.idmapper.models.SharedMemoryModelBase``)
generates an ``is_active`` property wrapper for the ``db_is_active`` model
field on the bare ``ScriptDB`` class itself, so it is always present,
typeclassed or not.
"""

from __future__ import annotations

from typing import Any

from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.scripts.models import ScriptDB
from evennia.utils import logger

# Imported straight from each app's `models` module rather than via the
# `evennia.ObjectDB` / `evennia.AccountDB` / `evennia.ScriptDB` top-level
# lazy attributes: those start as `None` and are only populated by
# Evennia's own `evennia._init()`, which runs later than Django's app
# loading. `install_lifecycle_hook_guards()` runs from an AppConfig.ready(),
# so at that point the lazy attributes are still `None` -- the real model
# classes, imported directly, are already available because Django
# populates every app's models before calling any app's ready().

# Hooks the shutdown/reload path in evennia/server/service.py calls directly
# on cached instances, per class. Enumerated by reading shutdown() line by
# line (2026-08-16): ObjectDB.at_server_reload/at_server_shutdown,
# AccountDB.at_server_reload/at_server_shutdown/unpuppet_all,
# ScriptDB.at_server_reload/at_server_shutdown/_pause_task. The
# `_SA(p, "is_connected", False)` call uses `object.__setattr__` directly, and
# `ScriptDB.is_active` is a model-level property (see module docstring), so
# neither needs a guard.
_GUARDED_CLASSES = {
    ObjectDB: ("at_server_reload", "at_server_shutdown"),
    AccountDB: ("at_server_reload", "at_server_shutdown", "unpuppet_all"),
    ScriptDB: ("at_server_reload", "at_server_shutdown", "_pause_task"),
}


def _make_noop_hook(class_name: str, attr_name: str) -> Any:
    """Build a logging no-op to stand in for a missing lifecycle hook.

    Args:
        class_name: Name of the bare model class the stub is installed on.
        attr_name: Name of the missing hook/method.

    Returns:
        A function suitable for use as an unbound method: it accepts and
        ignores any positional/keyword arguments the real hook would have
        received, so it matches upstream's no-op (``pass``-bodied) semantics
        regardless of call signature.
    """

    def _noop(self: Any, *_args: Any, **_kwargs: Any) -> None:
        logger.log_warn(
            f"typeclass_hook_guard: {class_name} pk={self.pk} has no '{attr_name}'. "
            "This instance is running bare, not as its typeclass -- every custom "
            "hook and method on its real typeclass is silently absent for it. "
            "See issue #3195."
        )

    _noop.__name__ = f"guarded_{attr_name}"
    _noop.__doc__ = (
        f"typeclass_hook_guard no-op stand-in for a missing '{attr_name}'. See issue #3195."
    )
    return _noop


def install_lifecycle_hook_guards() -> None:
    """Patch bare Evennia model classes with no-ops for missing lifecycle hooks.

    Idempotent and safe to call more than once: only ever adds an attribute
    that is genuinely absent from the bare class, and never overwrites an
    attribute that already exists (whether it is a real hook, an inherited
    typeclass override, or a guard installed by an earlier call).
    """
    for cls, attr_names in _GUARDED_CLASSES.items():
        for attr_name in attr_names:
            if not hasattr(cls, attr_name):
                setattr(cls, attr_name, _make_noop_hook(cls.__name__, attr_name))
