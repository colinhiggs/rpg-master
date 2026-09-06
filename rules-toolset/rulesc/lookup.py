# lookup.py - finding a ruleset, and reading its version.
#
# Split out of build.py so that every tool resolves a ruleset the same
# way by importing one implementation, rather than each carrying its
# own copy of a two-place search that then drifts.

import os
import re
from pathlib import Path

from .compile import RuleError

TOOLSET_ROOT = Path(__file__).parent.parent      # .../rpg-master/rules-toolset

# A ruleset can sit in either of two places, and the difference is what
# stage it is at rather than what it is:
#
#   INSTALLED  rpg-master/rules/<name>   dropped in to be played. This is
#                                        the plug-in directory the game
#                                        ships with, and it is inside the
#                                        software repository.
#   WORKING    ../rules/<name>           a ruleset being AUTHORED, in the
#                                        outer working directory, usually
#                                        its own repository (ico is).
#
# Installed wins when a name exists in both, so a dropped-in ruleset is
# what actually runs; --path overrides everything.
INSTALLED_RULESETS = TOOLSET_ROOT.parent / "rules"
WORKING_RULESETS = TOOLSET_ROOT.parent.parent / "rules"
RULESET_SEARCH_PATH = (INSTALLED_RULESETS, WORKING_RULESETS)


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def read_version(ruleset_dir: Path):
    """Return the ruleset's version string, or None if it has no VERSION
    file.

    A version matters to anything built ON a ruleset rather than in it —
    an adventure, a campaign, a character sheet — which needs to say
    which rules it was checked against. The git tag alone cannot answer
    that, because the three build outputs travel to those consumers
    without their repository; so the version is stamped into all three,
    and the tag is a mirror of the VERSION file rather than the other
    way round.

    A ruleset without the file simply is not versioned, which is the
    right answer for a scratch or demonstration ruleset, and the outputs
    then carry no `_version` at all."""
    path = ruleset_dir / "VERSION"
    if not path.exists():
        return None
    version = path.read_text(encoding="utf-8").strip()
    if not VERSION_RE.match(version):
        raise RuleError(
            f"{path} contains {version!r}, which is not MAJOR.MINOR.PATCH. "
            "A version consumers compare has to be comparable."
        )
    return version


def find_ruleset(name: str):
    """Return (path, where) for a ruleset name, or (None, None)."""
    for root, where in zip(RULESET_SEARCH_PATH, ("installed", "working")):
        candidate = root / name
        if candidate.exists():
            return candidate, where
    return None, None


def resolve_ruleset_dir(args):
    if args.path:
        return Path(args.path), "path"
    return find_ruleset(args.ruleset)
