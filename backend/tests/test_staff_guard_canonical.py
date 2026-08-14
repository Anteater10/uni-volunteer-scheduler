"""S-03 — one spelling of "staff", enforced.

The W5 sweep found six ways of saying "admin or organizer" across the routers,
plus in-body checks in two files. That is not a vulnerability; it is the reason
K33 stayed hidden and the reason the sweep's own first pass mis-scoped its target
list by 20 endpoints. No single search covers the surface, so any future audit —
or anyone inheriting this code — starts by rediscovering that fact.

After the cleanup there is exactly one definition of the staff role set,
`deps.STAFF_ROLES`, and two dependencies built from it:

    require_admin  = require_role(UserRole.admin)
    require_staff  = require_role(*STAFF_ROLES)

These tests fail on a new spelling. They are deliberately source-level: the
problem is not what the code *does* — every spelling behaves correctly — but that
the surface cannot be read. A behavioural test cannot see that.

After the cleanup no router does its own role check. `signups.py` had four —
cancel, ICS export, and the two swap endpoints — all of them plain "staff only",
all of them invisible in the signature; they are dependencies now. The only
in-body checks left are inside `deps.py`, which is where they belong.

Exceptions are listed explicitly below rather than pattern-matched, so adding one
is a decision someone has to write down here. Two guards deliberately keep their
own wording while reading STAFF_ROLES for the role set: `deps.is_staff` (a
predicate, because anonymous callers reach those endpoints and simply see less)
and `copilot.router._require_admin_or_organizer` (its 403 names the copilot).
"""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# Files allowed to name the two staff roles side by side. deps.py defines the
# canonical set; the copilot router keeps its own 403 copy ("Copilot is
# restricted to admin and organizer accounts") but must build it from STAFF_ROLES.
_ROLE_TUPLE_ALLOWED = {"deps.py"}

# Handlers whose check genuinely is not "staff only". Each entry is a promise
# that the check expresses something require_role cannot.
_IN_BODY_ALLOWED = {
    "deps.py",  # require_role's own body, and is_staff's Optional-tolerant check
}

# deps.py defines require_role and names the forbidden pattern in its docstring.
_INLINE_DEPENDENCY_ALLOWED = {"deps.py"}

_STAFF_PAIR = re.compile(
    r"UserRole\.admin,\s*(models\.)?UserRole\.organizer"
    r"|UserRole\.organizer,\s*(models\.)?UserRole\.admin"
)
_IN_BODY_ROLE_CHECK = re.compile(r"current_user\.role\s+not\s+in|actor\.role\s+not\s+in")


def _sources():
    for path in sorted(APP.rglob("*.py")):
        yield path.relative_to(APP).as_posix(), path.read_text()


def test_the_staff_role_pair_is_named_in_one_place():
    offenders = sorted(
        name for name, src in _sources()
        if _STAFF_PAIR.search(src) and name not in _ROLE_TUPLE_ALLOWED
    )

    assert offenders == [], (
        "These files spell out the staff role pair instead of using "
        "deps.STAFF_ROLES / Depends(require_staff): " + ", ".join(offenders)
    )


def test_no_router_builds_a_role_dependency_inline():
    """`Depends(require_role(...))` at a call site is how the spellings multiply.

    Constructing the dependency inline is what let arg order, import style and
    role sets drift per endpoint. Build it once, name it, reuse the name.
    """
    offenders = sorted(
        name for name, src in _sources()
        if "Depends(require_role(" in src and name not in _INLINE_DEPENDENCY_ALLOWED
    )

    assert offenders == [], (
        "These files construct a role dependency inline instead of using a named "
        "one from deps: " + ", ".join(offenders)
    )


def test_in_body_staff_checks_are_confined_to_the_declared_exceptions():
    offenders = sorted(
        name for name, src in _sources()
        if _IN_BODY_ROLE_CHECK.search(src) and name not in _IN_BODY_ALLOWED
    )

    assert offenders == [], (
        "A role check in the handler body is invisible to anyone reading the "
        "signature — which is exactly how the sweep mis-scoped itself. Move it "
        "to a dependency, or add it to _IN_BODY_ALLOWED with the reason: "
        + ", ".join(offenders)
    )


def test_the_canonical_dependencies_exist_and_agree():
    """Guards against the aliases drifting apart from the constant."""
    from app import models
    from app.deps import STAFF_ROLES

    assert set(STAFF_ROLES) == {models.UserRole.admin, models.UserRole.organizer}
