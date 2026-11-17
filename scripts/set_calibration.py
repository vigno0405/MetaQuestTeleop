"""Make a calibration the library's: its points become those of ``adapt.CALIBRATION``
(src/metaquest_teleop/adapt.py) and of the 3D view (src/metaquest_teleop/view.html), for every
joint it has; the other joints keep theirs.

    python scripts/set_calibration.py ~/.config/metaquest-teleop/calibrations/adapt-2026-11-17-103000.json

Then run the tests, say so in CHANGELOG.md, and release.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PYTHON = re.compile(r"^CALIBRATION = \{\n.*?^\}  # fmt: skip$", re.S | re.M)
_JS = re.compile(r"^const ADAPT_CALIBRATION = \{\n.*?^\};$", re.S | re.M)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="a calibration, as metaquest-teleop --calibration saves it")
    parser.add_argument("--root", type=Path, default=ROOT, help="the repository (default: this script's)")
    args = parser.parse_args(argv)
    package = args.root / "src" / "metaquest_teleop"
    if (package / "__init__.py").is_file():
        sys.path.insert(0, str(args.root / "src"))
    from metaquest_teleop import adapt  # noqa: PLC0415 -- its joints, and how it checks points

    source, page = package / "adapt.py", package / "view.html"
    python, js = source.read_text(encoding="utf-8"), page.read_text(encoding="utf-8")
    in_python, in_js = _PYTHON.search(python), _JS.search(js)
    if in_python is None or in_js is None:
        print(f"No calibration found in {source if in_python is None else page}")
        return 1
    library = ast.literal_eval(in_python.group(0).split("=", 1)[1].rsplit("#", 1)[0])
    try:
        saved = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("expected {joint: points, ...}")
        new = {joint: adapt._points(joint, rows) for joint, rows in saved.items()}
    except (OSError, ValueError) as exc:
        print(f"{args.file} is not an ADAPT calibration: {exc}")
        return 1
    changed = [(j, library.get(j, {}), new[j]) for j in adapt.JOINTS if j in new and new[j] != library.get(j)]
    library.update(new)

    def number(v) -> str:
        return repr(adapt._number(v))

    def key(k) -> str:
        return "(" + ", ".join(number(x) for x in k) + ")" if isinstance(k, tuple) else number(k)

    groups = [g for g in (adapt.JOINTS[0:2], adapt.JOINTS[2:4], *(adapt.JOINTS[i:i + 4] for i in range(4, 20, 4)))
              if any(j in library for j in g)]
    python_block = "\n".join(
        ["CALIBRATION = {"]
        + ["    " + ", ".join(f'"{j}": {{' + ", ".join(f"{key(k)}: {number(v)}" for k, v in library[j].items()) + "}"
                              for j in g if j in library) + "," for g in groups]
        + ["}  # fmt: skip"])
    js_block = "\n".join(
        ["const ADAPT_CALIBRATION = {"]
        + ["  " + ", ".join(f"{j}: {json.dumps(adapt._rows(library[j]))}" for j in g if j in library) + "," for g in groups]
        + ["};"])
    python = python[:in_python.start()] + python_block + python[in_python.end():]
    js = js[:in_js.start()] + js_block + js[in_js.end():]
    if not changed:
        print("The library already has this calibration: nothing to change.")
        return 0
    source.write_text(python, encoding="utf-8")
    page.write_text(js, encoding="utf-8")
    for joint, before, after in changed:
        print(f"{joint}: {adapt._rows(before)} -> {adapt._rows(after)}")
    print(f"Changed {source} and {page}: now run the tests, say so in CHANGELOG.md, and release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
