"""Behavioral reference for the architectural register storage interface.

Reset values for architecturally undefined bits are project choices. This model
does not fetch the reset vector or decode instructions. SP is a pointer, not RAM.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RegisterState:
    a: int
    pc: int
    p: int
    x: int = 0
    y: int = 0
    e: int = 0
    d: int = 0
    dbr: int = 0
    pbr: int = 0
    sp: int = 0x01FF


RESET_STATE = RegisterState(0, 0, 0x34, e=1)


def masked_status(previous, value, mask):
    # Select each bit independently instead of copying the RTL bitwise formula.
    return sum(
        ((value if mask & (1 << bit) else previous) >> bit & 1) << bit
        for bit in range(8)
    )


def expected_mode_update(previous, inputs):
    """One legal update; E/P constraints use values committed on this edge."""
    new_e = inputs.get("e", 0) if inputs.get("e_write", False) else previous.e
    new_p = (
        masked_status(previous.p, inputs.get("p", 0), inputs.get("p_mask", 0xFF))
        if inputs.get("p_write", False) else previous.p
    )
    if new_e:
        new_p |= 0x30

    new_a = previous.a
    if inputs.get("a8", False):
        new_a = (previous.a // 256) * 256 + inputs["a"] % 256
    elif inputs.get("a16", False):
        new_a = inputs["a"]
    new_pc = (
        inputs["pc"] if inputs.get("pc_write", False)
        else (previous.pc + int(inputs.get("pc_inc", False))) % 65536
    )
    indexes = {}
    for register in ("x", "y"):
        enabled = inputs.get(f"{register}8", False) or inputs.get(f"{register}16", False)
        value = inputs[register] if enabled else getattr(previous, register)
        if inputs.get(f"{register}8", False) or new_p & 0x10:
            value %= 256
        indexes[register] = value

    new_sp = previous.sp
    if inputs.get("sp_write", False):
        new_sp = inputs["sp"]
    else:
        new_sp += int(inputs.get("sp_inc", False)) - int(inputs.get("sp_dec", False))
        new_sp %= 65536
    if new_e:
        new_sp = 0x0100 + new_sp % 256

    other_registers = {
        register: inputs[register] if inputs.get(f"{register}_write", False)
        else getattr(previous, register)
        for register in ("d", "dbr", "pbr")
    }
    return replace(previous, a=new_a, pc=new_pc, p=new_p, e=new_e, sp=new_sp,
                   **indexes, **other_registers)
