from functools import lru_cache
from importlib import import_module
from typing import Callable, Dict


@lru_cache(maxsize=None)
def get_package_hooks(module_path: str) -> Dict[str, Callable]:
    """Return hook functions defined in ``module_path``.

    The hooks dictionary is cached so repeated calls avoid re-importing the module.
    """
    module = import_module(module_path)
    return getattr(module, "hooks", {})
