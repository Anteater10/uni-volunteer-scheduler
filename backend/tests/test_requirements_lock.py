"""BASE-CONFIG-33: the lockfile has to stay in step with requirements.txt.

`requirements.txt` pins the ~60 packages we chose; roughly 55 more arrive as
transitive dependencies and were unpinned, so two builds of the same commit
could install different torch/transformers/openai versions. The image now builds
from `requirements.lock.txt`.

That introduces one new failure mode, which is what these tests exist for: bump
a version in requirements.txt, forget to regenerate the lock, and the build
silently keeps installing the old version — the pin you wrote has no effect and
nothing says so. The regeneration command is in the lockfile's header.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REQUIREMENTS = BACKEND / "requirements.txt"
LOCKFILE = BACKEND / "requirements.lock.txt"

_NAME = re.compile(r"^([A-Za-z0-9._-]+)")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _entries(path: Path) -> dict[str, str | None]:
    """Map normalized package name -> pinned version (None if unpinned)."""
    out: dict[str, str | None] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        line = line.split(";")[0].strip()  # drop environment markers
        match = _NAME.match(line)
        if not match:
            continue
        name = _normalize(match.group(1))
        pinned = line.split("==")[1].strip() if "==" in line else None
        out[name] = pinned
    return out


def test_the_lockfile_exists_and_pins_everything():
    assert LOCKFILE.exists(), "the image builds from this file"
    unpinned = [n for n, v in _entries(LOCKFILE).items() if v is None]
    assert not unpinned, f"lockfile entries without an exact version: {unpinned}"


def test_the_cpu_wheel_index_survives_regeneration():
    """torch is pinned as a +cpu local version, which pip cannot resolve from
    PyPI alone — dropping this line breaks the build outright, and it is exactly
    the kind of header a naive `pip freeze >` would wipe."""
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in (
        LOCKFILE.read_text()
    )


def test_every_package_we_chose_is_in_the_lockfile():
    missing = sorted(set(_entries(REQUIREMENTS)) - set(_entries(LOCKFILE)))
    assert not missing, (
        f"in requirements.txt but not locked: {missing} — regenerate the lock "
        "(command is in its header)"
    )


def test_no_explicit_pin_disagrees_with_the_lockfile():
    """The failure this is really about: a bumped version in requirements.txt
    that the lock still holds at the old one. The build uses the lock, so the
    bump would do nothing and no error would say so."""
    locked = _entries(LOCKFILE)
    conflicts = [
        (name, chosen, locked[name])
        for name, chosen in _entries(REQUIREMENTS).items()
        if chosen is not None and name in locked and locked[name] != chosen
    ]
    assert not conflicts, (
        "requirements.txt and requirements.lock.txt disagree "
        f"(name, requirements.txt, lock): {conflicts}"
    )
