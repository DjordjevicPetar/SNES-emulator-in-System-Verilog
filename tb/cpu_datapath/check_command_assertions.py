"""An invalid command must stop only after the normal setup has succeeded."""

import os
import subprocess
import sys


def disable_core_dump():
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


cases = {
    "load_execute": "ASSERT_DP_A_CONFLICT",
    "load_p": "ASSERT_DP_CONTROL_CONFLICT",
    "execute_p": "ASSERT_DP_CONTROL_CONFLICT",
    "load_e": "ASSERT_DP_CONTROL_CONFLICT",
    "execute_e": "ASSERT_DP_CONTROL_CONFLICT",
    "invalid_op": "ASSERT_DP_INVALID_OP",
    "decimal_adc": "ASSERT_DP_DECIMAL_UNSUPPORTED",
    "decimal_sbc": "ASSERT_DP_DECIMAL_UNSUPPORTED",
}
failures = 0
for mode in ("emulation", "native16"):
    for name, message in cases.items():
        result = subprocess.run(
            [sys.argv[1], f"+case={name}", f"+mode={mode}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10,
            preexec_fn=disable_core_dump if os.name == "posix" else None,
        )
        rejected = (result.returncode != 0 and "BEGIN_INVALID_COMMAND" in result.stdout
                    and message in result.stdout and "COMMAND_WAS_NOT_REJECTED" not in result.stdout)
        if rejected:
            print(f"PASS: {mode} {name} rejected")
        else:
            failures += 1
            print(result.stdout)
            print(f"FAIL: {mode} {name} was not rejected by {message}")
if failures:
    raise SystemExit(f"FAIL: {failures}/16 datapath assertion checks failed")
