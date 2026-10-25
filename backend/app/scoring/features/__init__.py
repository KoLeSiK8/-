

from importlib import import_module
from pkgutil import iter_modules

for _module in sorted(iter_modules(__path__), key=lambda item: item.name):
    if not _module.name.startswith("_"):
        import_module(f"{__name__}.{_module.name}")
