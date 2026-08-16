import sys
import types

from .application import ROUTER_MODULES, create_app
from .core import legacy as _legacy
from .core.legacy import *


app = create_app()
_legacy.app = app


def _sync_split_module_global(name: str, value) -> None:
    setattr(_legacy, name, value)
    for module_name in ROUTER_MODULES:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            types.ModuleType.__setattr__(module, name, value)


class _MainCompatibilityModule(types.ModuleType):
    def __getattr__(self, name: str):
        return getattr(_legacy, name)

    def __setattr__(self, name: str, value) -> None:
        types.ModuleType.__setattr__(self, name, value)
        if name not in {"ROUTER_MODULES", "_legacy"}:
            _sync_split_module_global(name, value)

    def __delattr__(self, name: str) -> None:
        types.ModuleType.__delattr__(self, name)
        if hasattr(_legacy, name):
            delattr(_legacy, name)
        for module_name in ROUTER_MODULES:
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, name):
                types.ModuleType.__delattr__(module, name)


sys.modules[__name__].__class__ = _MainCompatibilityModule
