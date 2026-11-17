import importlib.machinery
import importlib.util
import os
import pathlib
import tempfile

# Every cache path agsearch builds comes from XDG_CACHE_HOME when it is imported. A test that
# redirects only some of them (upstream's test_expired once missed three) would write the rest
# into the real ~/.cache/ccfind, so the whole suite is pointed at a throwaway one.
_CACHE = tempfile.TemporaryDirectory(prefix="ccfind-unit-")
os.makedirs(os.path.join(_CACHE.name, "ccfind"))    # the real one exists; tests rely on that


def load_agsearch():
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "agsearch"
    loader = importlib.machinery.SourceFileLoader("agsearch_under_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    saved = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = _CACHE.name
    try:
        loader.exec_module(module)
    finally:
        if saved is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = saved
    return module
