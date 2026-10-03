#!/usr/bin/env python
"""Vendor Pyodide and the engine's wheels, so the checker can run in a browser.

The static build (``ui/build_static.py``) runs the engine inside the page: the
Python interpreter is Pyodide (CPython compiled to WebAssembly), and the
engine's three dependencies are installed into it from wheels:

* SymPy and mpmath, from the Pyodide distribution (pure Python);
* Lark, from PyPI (pure Python);
* z3-solver, from PyPI -- z3 publishes a WebAssembly wheel built for this
  Pyodide ABI (``pyemscripten_2026_0_wasm32``).

Everything is pinned and checked against a sha256, like a lockfile.  The set is
about 30 MB of binaries, so it is *not* committed: this script fetches it into
``ui/static/vendor/pyodide/`` (gitignored).  The development server
(``python -m ui``) does not need it; only the static build and
``ui/verify_wasm.mjs`` do.

No npm is involved: the Pyodide core comes from the npm registry as a tarball
and is read with the standard library, as ``vendor_webawesome.py`` does.

Run with:  uv run python ui/vendor_pyodide.py
"""

from __future__ import annotations

import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

PYODIDE_VERSION = "314.0.7"
TARBALL_URL = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz"
CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full"

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "static" / "vendor" / "pyodide"

# The runtime itself: what loadPyodide() fetches.
CORE = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]

# file name -> (url, sha256)
WHEELS = {
    "sympy-1.14.0-py3-none-any.whl": (
        f"{CDN}/sympy-1.14.0-py3-none-any.whl",
        "61ea8bb98049ba1c702ba3ad2607acb7ab94b9af0b6f97498741f50d3249f428",
    ),
    "mpmath-1.4.1-py3-none-any.whl": (
        f"{CDN}/mpmath-1.4.1-py3-none-any.whl",
        "e5ebd537e74b9066341a5152e83b63ff2fc37a6388fa7351e766b6e4640f7eee",
    ),
    "lark-1.3.1-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/82/3d/14ce75ef66813643812f3093ab17e46d3a206942ce7376d31ec2d36229e7/lark-1.3.1-py3-none-any.whl",
        "c629b661023a014c37da873b4ff58a817398d12635d3bbb2c5a03be7fe5d1e12",
    ),
    "z3_solver-5.1.0.0-py3-none-pyemscripten_2026_0_wasm32.whl": (
        "https://files.pythonhosted.org/packages/08/2c/842c3ca4ce8e503a5095c1883e0f18d45e202b1c75451a807ee3a6e4b83e/z3_solver-5.1.0.0-py3-none-pyemscripten_2026_0_wasm32.whl",
        "d49a91527dc4f65e4a5a938b86a16937decadcbdbd806833d28ce25eb24cd3a9",
    ),
}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def main() -> int:
    staging = DEST.with_name("pyodide.tmp")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    print(f"pyodide {PYODIDE_VERSION}: {TARBALL_URL}")
    with tarfile.open(fileobj=io.BytesIO(fetch(TARBALL_URL)), mode="r:gz") as tar:
        for name in CORE:
            member = tar.extractfile(f"package/{name}")
            if member is None:
                print(f"  missing from the tarball: {name}")
                return 1
            (staging / name).write_bytes(member.read())
            print(f"  {name}")

    wheels = staging / "wheels"
    wheels.mkdir()
    for name, (url, sha256) in WHEELS.items():
        data = fetch(url)
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256:
            print(f"  {name}: sha256 {digest} does not match the pin {sha256}")
            return 1
        (wheels / name).write_bytes(data)
        print(f"  wheels/{name}")

    # Only replace the vendored set once everything arrived and verified.
    shutil.rmtree(DEST, ignore_errors=True)
    staging.rename(DEST)
    total = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"vendored into {DEST.relative_to(ROOT.parent)} ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
