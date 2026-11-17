import importlib.machinery
import importlib.util
import os
import pathlib
import tempfile

# Every cache path agsearch builds comes from XDG_CACHE_HOME when it is imported, and the saved
# account list from XDG_CONFIG_HOME. A test that redirects only some of them (upstream's
# test_expired once missed three) would write the rest into the real ~/.cache/ccfind and
# ~/.config/ccfind, so the whole suite is pointed at a throwaway pair.
_CACHE = tempfile.TemporaryDirectory(prefix="ccfind-unit-")
os.makedirs(os.path.join(_CACHE.name, "ccfind"))    # the real one exists; tests rely on that
_CONFIG = tempfile.TemporaryDirectory(prefix="ccfind-unit-config-")
_ENV = {"XDG_CACHE_HOME": _CACHE.name, "XDG_CONFIG_HOME": _CONFIG.name}


def load_agsearch():
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "agsearch"
    loader = importlib.machinery.SourceFileLoader("agsearch_under_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    saved = {k: os.environ.get(k) for k in _ENV}
    os.environ.update(_ENV)
    try:
        loader.exec_module(module)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return module
