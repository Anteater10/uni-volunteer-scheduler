"""Report coverage of ONLY the lines this branch changed.

Whole-file coverage cannot answer "did we test what we just wrote" — a file
can sit at 94% while every new line is in the missing 6%, which is exactly
how a showstopper shipped in this phase. This intersects the added/modified
line numbers from `git diff` with coverage.py's missing-line set, so the
number it prints is the one that matters for a change under review.

Usage (from the repo root, after a run with --cov-report=json):
    python3 backend/tools/changed_line_coverage.py <base-ref> <coverage.json> [path ...]
"""
import json
import subprocess
import sys
from collections import defaultdict


def changed_lines(base_ref, paths):
    """Map file -> set of line numbers added or modified vs base_ref.

    Parses `git diff -U0` hunk headers. Deletions are irrelevant here: a line
    that no longer exists cannot be covered.
    """
    cmd = ["git", "diff", "-U0", base_ref, "--"] + list(paths)
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    result = defaultdict(set)
    current = None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("@@") and current:
            # @@ -old,+new @@ ; we want the +new side
            plus = line.split("+")[1].split("@@")[0].strip()
            if "," in plus:
                start, count = plus.split(",")
                start, count = int(start), int(count)
            else:
                start, count = int(plus), 1
            for n in range(start, start + count):
                result[current].add(n)
    return result


def main():
    base_ref, cov_path = sys.argv[1], sys.argv[2]
    paths = sys.argv[3:] or ["backend/app"]

    changed = changed_lines(base_ref, paths)
    cov = json.load(open(cov_path))["files"]

    # coverage.json keys are relative to the pytest rootdir (backend/), while
    # git paths are repo-relative. Normalise by stripping the backend/ prefix.
    def cov_key(git_path):
        return git_path[len("backend/") :] if git_path.startswith("backend/") else git_path

    untracked_note = []
    total_changed = total_missed = 0
    print(f"{'file':<45} {'changed':>8} {'missed':>7}  uncovered changed lines")
    print("-" * 100)
    for git_path in sorted(changed):
        key = cov_key(git_path)
        entry = cov.get(key)
        if entry is None:
            untracked_note.append(git_path)
            continue
        missing = set(entry["missing_lines"])
        # missing_branches is a list of [source_line, dest_line] pairs — a
        # branch out of source_line that was never taken. Attribute it to the
        # source line, which is the one a reader has to go look at.
        partial = {
            pair[0]
            for pair in (entry.get("missing_branches") or [])
            if isinstance(pair, (list, tuple)) and pair
        }
        changed_here = changed[git_path]
        missed_here = sorted((missing | partial) & changed_here)
        total_changed += len(changed_here)
        total_missed += len(missed_here)
        shown = ", ".join(str(n) for n in missed_here) if missed_here else "—"
        print(f"{git_path:<45} {len(changed_here):>8} {len(missed_here):>7}  {shown}")

    print("-" * 100)
    covered = total_changed - total_missed
    pct = (covered / total_changed * 100) if total_changed else 100.0
    print(f"changed executable-or-comment lines: {total_changed}")
    print(f"uncovered among them:                {total_missed}")
    print(f"CHANGED-LINE COVERAGE:               {pct:.1f}%")
    if untracked_note:
        print("\nnot in the coverage report (not imported, or non-Python):")
        for p in untracked_note:
            print(f"  {p}")
    # Note: `changed` counts every diff line including comments/blank lines,
    # which coverage.py does not track at all — so a line absent from both
    # missing_lines and executed_lines is simply not executable. The number
    # that matters is `uncovered among them`, which only ever contains lines
    # coverage.py itself flagged as missed.
    return 1 if total_missed else 0


if __name__ == "__main__":
    sys.exit(main())
