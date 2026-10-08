#!/usr/bin/env python3
"""Pick which files of a Hugging Face repo to download.

    hf_pick.py <repo> <model patterns> [<mmproj patterns>]

Each pattern argument is a space-separated list of glob patterns tried in order
(case-insensitive); the first one that matches wins. Prints the chosen file paths,
one per line. If no model file matches, lists the repo's .gguf files and exits 2.
"""

from __future__ import annotations

import fnmatch
import sys

from huggingface_hub import list_repo_files


def pick(files: list[str], patterns: str, *, mmproj: bool) -> list[str]:
    candidates = [f for f in files if f.lower().endswith(".gguf")
                  and ("mmproj" in f.lower().rsplit("/", 1)[-1]) == mmproj]
    for pattern in patterns.split():
        hits = sorted(f for f in candidates if fnmatch.fnmatch(f.lower(), pattern.lower()))
        if hits:
            if mmproj:
                return hits[:1]
            # Split models (-00001-of-00003) need every part, but only one quant folder/prefix.
            first = hits[0]
            prefix = first.split("-00001-of-")[0] if "-00001-of-" in first else None
            return [f for f in hits if prefix and f.startswith(prefix)] or [first]
    return []


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    repo, model_patterns = sys.argv[1], sys.argv[2]
    mmproj_patterns = sys.argv[3] if len(sys.argv) > 3 else ""
    try:
        files = list_repo_files(repo)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: can't list files in {repo}: {e}", file=sys.stderr)
        return 1

    model = pick(files, model_patterns, mmproj=False)
    if not model:
        print(f"ERROR: none of '{model_patterns}' matched a model file in {repo}.", file=sys.stderr)
        print("GGUF files in the repo:", file=sys.stderr)
        for f in sorted(f for f in files if f.lower().endswith(".gguf")):
            print(f"  {f}", file=sys.stderr)
        return 2
    chosen = list(model)
    if mmproj_patterns:
        mm = pick(files, mmproj_patterns, mmproj=True)
        if mm:
            chosen += mm
        else:
            print(f"WARNING: no mmproj file matched '{mmproj_patterns}'; image input will be off.",
                  file=sys.stderr)
    print("\n".join(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
