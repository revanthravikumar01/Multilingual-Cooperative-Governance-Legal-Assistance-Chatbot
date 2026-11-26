"""Skip IndicF5's training-only imports (datasets -> pyarrow dataset DLL is blocked by Smart App Control)."""
import sys
import types


def install():
    for name in ("datasets",):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.Dataset = mod.load_dataset = mod.load_from_disk = mod.Dataset_ = object
            sys.modules[name] = mod
