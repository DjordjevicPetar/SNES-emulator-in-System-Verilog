"""A deliberate assertion failure is a PASS only after the illegal request."""

import os
import subprocess
import sys
from itertools import product


def disable_core_dump():
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


cases = [(mode, register, False)
         for mode, register in product(("native", "emulation"), ("A", "X", "Y"))]
cases += [(mode, "SP", write)
          for mode, write in product(("native", "emulation"), (False, True))]
failures = 0
for mode, register, stack_write in cases:
    result = subprocess.run(
        [sys.argv[1], f"+conflict={register}", f"+mode={mode}",
         f"+stack_write={int(stack_write)}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
        preexec_fn=disable_core_dump if os.name == "posix" else None,
    )
    # SP's assertion text is up to the RTL author. Only SP controls conflict in
    # that case, and the normal setup has already passed before the BEGIN marker.
    message = "Assertion failed" if register == "SP" else f"ASSERT_{register}_WRITE_CONFLICT"
    expected_failure = (
        result.returncode != 0
        and f"BEGIN_INVALID_{register}_WRITE" in result.stdout
        and message in result.stdout
        and f"INVALID_{register}_WRITE_WAS_NOT_REJECTED" not in result.stdout
    )
    if not expected_failure:
        failures += 1
        print(result.stdout)
        print(f"FAIL: {register} conflict in {mode}, SP write={stack_write}, was not rejected")
    else:
        print(f"PASS: {register} conflict in {mode}, SP write={stack_write}, was rejected")
if failures:
    raise SystemExit(f"FAIL: {failures}/{len(cases)} assertion checks failed")
