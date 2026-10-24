"""Registered scoring features, one per module.

Every module in this package is imported automatically, so adding a feature only
takes a new file with a class decorated by @register_feature.
"""

from importlib import import_module
from pkgutil import iter_modules

for _module in sorted(iter_modules(__path__), key=lambda item: item.name):
    if not _module.name.startswith("_"):
        import_module(f"{__name__}.{_module.name}")
