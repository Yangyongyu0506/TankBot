"""Repository resources live in assets; old trusted configuration references are aliases."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"


def repository_path(reference):
    """Resolve a repository reference, redirecting former resource roots without copies.

    This does not grant access: callers retain their category-specific containment
    checks. Absolute custom level/config paths keep their existing semantics.
    """
    path = (ROOT / Path(reference)).resolve()
    for name in ("config", "levels", "templates", "examples"):
        legacy = ROOT / name
        if path.is_relative_to(legacy):
            return (ASSETS / name / path.relative_to(legacy)).resolve()
    return path
