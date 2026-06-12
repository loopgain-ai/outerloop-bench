#!/usr/bin/env python3
"""Pre-flight: prove the trial-generation machinery before spending tokens.

1. Each family's CLEAN sources pass their suite 100%.
2. Every catalog bug, applied alone, causes >=1 failure (and applies uniquely).
3. The naive hard modules fail a meaningful subset of their specs.
"""

import os
import pathlib
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).parent
# Interpreter for pytest + worker subprocesses. Defaults to the interpreter
# running this script; override with LOOPGAIN_PY to point at a venv that has
# `loopgain` + pytest installed.
VENV_PY = os.environ.get("LOOPGAIN_PY", sys.executable)

FAMILIES = {
    "textstats": ["textstats.py", "test_textstats.py"],
    "pipeline": ["money.py", "dates.py", "parsing.py", "report.py", "test_pipeline.py"],
    "orders": ["inventory.py", "orders.py", "test_orders.py"],
}
HARD = {
    "recur": ["recur.py", "test_recur.py"],
    "calcexpr": ["calcexpr.py", "test_calcexpr.py"],
}


def run_pytest(d):
    p = subprocess.run([VENV_PY, "-m", "pytest", "--tb=no", "-q"], cwd=d,
                       capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    return failed + errors, passed, out.strip().splitlines()[-1]


bad = 0
for fam, files in FAMILIES.items():
    src = ROOT / "families" / fam
    with tempfile.TemporaryDirectory() as td:
        for f in files:
            shutil.copy(src / f, pathlib.Path(td) / f)
        f_, p_, line = run_pytest(td)
        status = "OK" if f_ == 0 else "FAIL"
        if f_ != 0:
            bad += 1
        print(f"{fam} CLEAN: {status} ({line})")

    bugs = runpy.run_path(str(src / "bugs.py"))["BUGS"]
    for i, (fname, clean, buggy) in enumerate(bugs):
        with tempfile.TemporaryDirectory() as td:
            for f in files:
                shutil.copy(src / f, pathlib.Path(td) / f)
            path = pathlib.Path(td) / fname
            s = path.read_text()
            n = s.count(clean)
            if n != 1:
                print(f"  bug {i} ({fname}): SNIPPET COUNT {n} != 1  ** BAD **")
                bad += 1
                continue
            path.write_text(s.replace(clean, buggy))
            f_, p_, line = run_pytest(td)
            if f_ == 0:
                print(f"  bug {i} ({fname}): NO FAILURES  ** BAD **")
                bad += 1
            else:
                print(f"  bug {i} ({fname}): breaks {f_} test(s)")

for hm, files in HARD.items():
    with tempfile.TemporaryDirectory() as td:
        for f in files:
            shutil.copy(ROOT / "hard" / f, pathlib.Path(td) / f)
        f_, p_, line = run_pytest(td)
        print(f"hard/{hm} NAIVE: {f_} failing / {p_} passing ({line})")
        if f_ < 3:
            print(f"  ** hard module too easy at baseline **")
            bad += 1

print("\nVALIDATION:", "PASS" if bad == 0 else f"{bad} PROBLEM(S)")
sys.exit(1 if bad else 0)
