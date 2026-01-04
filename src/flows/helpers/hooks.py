from collections.abc import Callable
from functools import cache
from importlib import import_module


@cache
def get_package_hooks(module_path: str) -> dict[str, Callable]:
    """Return hook functions defined in ``module_path``.

    The hooks dictionary is cached so repeated calls avoid re-importing the module.
    """
    module = import_module(module_path)
    try:
        return module.hooks
    except AttributeError:
        return {}
