"""A/PC/P/X/Y/E storage, masked status writes, and mode transitions.

The register-block reset contract is A=PC=X=Y=D=DBR=PBR=0, SP=01FF, E=1, P=34.
Undefined hardware reset bits are assigned deterministic values here; vector
fetching is separate.
Most basic register tests explicitly enter native mode and clear P after reset.
E=1 forces M/X high after applying any masked P write, including when E itself
changes on the same clock edge. Leaving emulation does not restore old M/X bits.
P[4] must constrain X/Y using the status value committed on the same clock edge.
As a defensive interface choice, a 16-bit index write request is truncated when
the resulting P[4] is one. A future decoder should request an 8-bit write instead.
A still follows its explicit 8/16-bit write enables; M-based decoding is separate.
Assertions remain enabled. Illegal simultaneous 8/16-bit enables are checked in
a separate simulator process (make check-assertion), because they must abort it.
"""

import random
from dataclasses import replace

import cocotb
from cocotb.triggers import Timer

from cpu_register_driver import CpuRegisterDriver
from cpu_register_model import RegisterState, RESET_STATE, masked_status, expected_mode_update


async def start_registers(dut, *, native=True):
    registers = CpuRegisterDriver(dut)
    await registers.start()
    if native:
        await registers.enter_native()
    return registers


@cocotb.test()
@cocotb.parametrize(clock_level=[0, 1])
async def reset_initializes_every_register_without_a_clock_edge(dut, clock_level):
    registers = await start_registers(dut)
    await registers.cycle(
        a=0xABCD, a16=True, pc=0x4567, pc_write=True, p=0xEF, p_write=True,
        x=0x1357, x16=True, y=0x9BDF, y16=True,
        d=0xBEEF, d_write=True, dbr=0xA5, dbr_write=True,
        pbr=0x5A, pbr_write=True, sp=0xABCD, sp_write=True,
    )
    dut.clk_i.value = clock_level
    await Timer(2, unit="ns")
    assert registers.snapshot() == RegisterState(
        0xABCD, 0x4567, 0xEF, 0x1357, 0x9BDF,
        d=0xBEEF, dbr=0xA5, pbr=0x5A, sp=0xABCD,
    )
    await registers.reset()
    assert registers.snapshot() == RESET_STATE
    assert await registers.cycle() == RESET_STATE


@cocotb.test()
async def reset_has_priority_over_all_write_controls(dut):
    registers = await start_registers(dut)
    await registers.cycle(a=0x1234, a16=True, pc=0x5678, pc_write=True,
                          p=0xEF, p_write=True, x=0xABCD, x16=True,
                          y=0x2468, y16=True, d=0xBEEF, d_write=True,
                          dbr=0xA5, dbr_write=True, pbr=0x5A, pbr_write=True,
                          sp=0xABCD, sp_write=True)
    dut.reset_ni_i.value = 0
    registers.drive(a=0xFFFF, a8=True, a16=True, pc=0xFFFF, pc_write=True,
                    pc_inc=True, p=0xFF, p_write=True,
                    x=0xFFFF, x8=True, x16=True, y=0xFFFF, y8=True, y16=True,
                    e=0, e_write=True, d=0xFFFF, d_write=True,
                    dbr=0xFF, dbr_write=True, pbr=0xFF, pbr_write=True,
                    sp=0xFFFF, sp_write=True, sp_inc=True, sp_dec=True)
    for _ in range(3):
        assert await registers.tick() == RESET_STATE

    registers.drive()
    dut.reset_ni_i.value = 1
    assert await registers.tick() == RESET_STATE
    assert await registers.cycle(a=0xCDEF, a16=True) == replace(RESET_STATE, a=0xCDEF)


@cocotb.test()
async def full_accumulator_writes_store_all_sixteen_bits(dut):
    registers = await start_registers(dut)
    values = (0x0000, 0xFFFF, 0xAAAA, 0x5555, 0x1234)
    values += tuple(1 << bit for bit in range(16))
    for value in values:
        assert await registers.cycle(a=value, a16=True) == RegisterState(value, 0, 0)


@cocotb.test()
@cocotb.parametrize(high_byte=[0x00, 0x12, 0x80, 0xFF])
async def eight_bit_writes_preserve_the_accumulator_high_byte(dut, high_byte):
    registers = await start_registers(dut)
    await registers.cycle(a=(high_byte << 8) | 0xA5, a16=True,
                          pc=0x1234, pc_write=True, p=0xC3, p_write=True)
    for low_byte in range(256):
        # Feed a deliberately different upper byte: it must not overwrite A[15:8].
        value = ((high_byte ^ 0xFF) << 8) | low_byte
        expected_a = high_byte * 256 + low_byte
        assert await registers.cycle(a=value, a8=True) == RegisterState(
            expected_a, 0x1234, 0xC3
        )


@cocotb.test()
async def disabled_writes_hold_state_despite_input_changes(dut):
    registers = await start_registers(dut)
    expected = RegisterState(0xA5C3, 0x2468, 0xB7)
    await registers.cycle(a=expected.a, a16=True, pc=expected.pc, pc_write=True,
                          p=expected.p, p_write=True)
    rng = random.Random(0xD15AB1E)
    for _ in range(128):
        assert await registers.cycle(
            a=rng.randrange(65536), pc=rng.randrange(65536),
            p=rng.randrange(256), p_mask=rng.randrange(256),
        ) == expected


@cocotb.test()
async def inputs_only_take_effect_at_a_rising_clock_edge(dut):
    registers = await start_registers(dut)
    dut.clk_i.value = 0
    registers.drive(a=0xBEEF, a16=True, pc=0x4567, pc_write=True, p=0xA5, p_write=True)
    await Timer(4, unit="ns")
    assert registers.snapshot() == RegisterState(0, 0, 0)
    assert await registers.tick() == RegisterState(0xBEEF, 0x4567, 0xA5)

    registers.drive(a=0x1357, a16=True, pc=0xABCD, pc_write=True, p=0x5A, p_write=True)
    await Timer(4, unit="ns")
    assert registers.snapshot() == RegisterState(0xBEEF, 0x4567, 0xA5)
    assert await registers.tick() == RegisterState(0x1357, 0xABCD, 0x5A)


@cocotb.test()
async def pc_write_takes_priority_over_increment(dut):
    registers = await start_registers(dut)
    for value in (0x0000, 0x0001, 0x1234, 0x8000, 0xFFFF):
        state = await registers.cycle(pc=value, pc_write=True, pc_inc=True)
        assert state == RegisterState(0, value, 0)


@cocotb.test()
async def pc_increment_wraps_at_sixteen_bits_and_can_be_disabled(dut):
    registers = await start_registers(dut)
    await registers.cycle(pc=0xFFFD, pc_write=True)
    for expected_pc in (0xFFFE, 0xFFFF, 0x0000, 0x0001):
        assert await registers.cycle(pc_inc=True) == RegisterState(0, expected_pc, 0)
        assert await registers.cycle(pc=0xAAAA) == RegisterState(0, expected_pc, 0)


@cocotb.test()
async def status_write_enable_gates_all_mask_bits(dut):
    registers = await start_registers(dut)
    await registers.cycle(p=0xA5, p_write=True)
    for mask in range(256):
        assert await registers.cycle(p=0x5A, p_mask=mask) == RegisterState(0, 0, 0xA5)


@cocotb.test()
async def every_status_mask_updates_only_selected_bits(dut):
    registers = await start_registers(dut)
    for previous in (0x00, 0xFF, 0xAA, 0x55):
        for value in (0x00, 0xFF, 0x3C, 0xC3):
            for mask in range(256):
                await registers.cycle(p=previous, p_write=True)
                expected = masked_status(previous, value, mask)
                state = await registers.cycle(p=value, p_write=True, p_mask=mask)
                assert state == RegisterState(0, 0, expected), (
                    f"P={previous:#04x}, data={value:#04x}, mask={mask:#04x}: "
                    f"expected {expected:#04x}, got {state.p:#04x}"
                )


@cocotb.test()
async def common_flag_masks_preserve_unaffected_cpu_flags(dut):
    registers = await start_registers(dut)
    await registers.cycle(p=0xFF, p_write=True)
    assert (await registers.cycle(p=0, p_write=True, p_mask=0x82)).p == 0x7D
    assert (await registers.cycle(p=0, p_write=True, p_mask=0xC3)).p == 0x3C
    assert (await registers.cycle(p=0xFF, p_write=True, p_mask=0)).p == 0x3C
    assert (await registers.cycle(p=0xA5, p_write=True, p_mask=0xFF)).p == 0xA5


@cocotb.test()
async def all_five_registers_can_update_on_the_same_edge(dut):
    registers = await start_registers(dut)
    assert await registers.cycle(
        a=0xABCD, a16=True, pc=0x1234, pc_write=True, p=0xEF, p_write=True,
        x=0x1357, x16=True, y=0x2468, y16=True,
    ) == RegisterState(0xABCD, 0x1234, 0xEF, 0x1357, 0x2468)
    assert await registers.cycle(
        a=0x0012, a8=True, pc_inc=True, p=0, p_write=True, p_mask=0x82,
        x=0xABCD, x8=True, y=0xEF01, y8=True,
    ) == RegisterState(0xAB12, 0x1235, 0x6D, 0x00CD, 0x0001)


@cocotb.test()
async def randomized_updates_match_independent_register_state(dut):
    registers = await start_registers(dut)
    expected = RegisterState(0, 0, 0)
    rng = random.Random(0x65816)
    for index in range(512):
        if index % 37 == 0:
            await registers.reset()
            await registers.enter_native()
            expected = RegisterState(0, 0, 0)

        a_mode = rng.randrange(3)
        inputs = dict(
            a=rng.randrange(65536), a8=a_mode == 1, a16=a_mode == 2,
            pc=rng.randrange(65536), pc_write=bool(rng.randrange(2)),
            pc_inc=bool(rng.randrange(2)), p=rng.randrange(256),
            p_write=bool(rng.randrange(2)), p_mask=rng.randrange(256),
        )
        next_a = expected.a
        if inputs["a8"]:
            next_a = (expected.a // 256) * 256 + inputs["a"] % 256
        elif inputs["a16"]:
            next_a = inputs["a"]
        next_pc = (
            inputs["pc"] if inputs["pc_write"]
            else (expected.pc + int(inputs["pc_inc"])) % 65536
        )
        next_p = (
            masked_status(expected.p, inputs["p"], inputs["p_mask"])
            if inputs["p_write"] else expected.p
        )
        expected = RegisterState(next_a, next_pc, next_p)
        observed = await registers.cycle(**inputs)
        assert observed == expected, (
            f"update {index}, inputs={inputs}: expected {expected}, got {observed}"
        )


async def seed_index_state(registers, index_flag=0):
    # Set the mode before the data, so ordinary write/hold tests do not depend
    # on the separate same-edge mode-transition tests below.
    await registers.cycle(p=index_flag << 4, p_write=True)
    expected = RegisterState(
        0xA5C3, 0x2468, index_flag << 4,
        0x003C if index_flag else 0xA53C,
        0x00C3 if index_flag else 0x5AC3,
    )
    observed = await registers.cycle(
        a=expected.a, a16=True, pc=expected.pc, pc_write=True,
        x=expected.x, x16=True, y=expected.y, y16=True,
    )
    assert observed == expected
    return expected


@cocotb.test()
@cocotb.parametrize(register=["x", "y"])
async def full_index_writes_store_all_bits_in_sixteen_bit_mode(dut, register):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers)
    values = (0, 1, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0xFFFF, 0xAAAA, 0x5555)
    values += tuple(1 << bit for bit in range(16))
    for value in values:
        expected = replace(expected, **{register: value})
        assert await registers.cycle(**{register: value, f"{register}16": True}) == expected


@cocotb.test()
@cocotb.parametrize(register=["x", "y"], index_flag=[0, 1])
async def eight_bit_index_writes_zero_the_upper_byte(dut, register, index_flag):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers, index_flag)
    for low_byte in range(256):
        value = ((low_byte ^ 0xFF) << 8) | low_byte
        expected = replace(expected, **{register: low_byte})
        observed = await registers.cycle(**{register: value, f"{register}8": True})
        assert observed == expected


@cocotb.test()
@cocotb.parametrize(index_flag=[0, 1])
async def disabled_index_writes_hold_both_registers(dut, index_flag):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers, index_flag)
    rng = random.Random(0x1D1E + index_flag)
    for _ in range(128):
        assert await registers.cycle(
            x=rng.randrange(65536), y=rng.randrange(65536),
            p=rng.randrange(256), p_mask=rng.randrange(256),
        ) == expected


@cocotb.test()
async def index_inputs_only_take_effect_at_a_rising_edge(dut):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers)
    dut.clk_i.value = 0
    registers.drive(x=0x1234, x16=True, y=0x5678, y16=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    expected = replace(expected, x=0x1234, y=0x5678)
    assert await registers.tick() == expected

    registers.drive(x=0xABCD, x8=True, y=0xEF01, y8=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    assert await registers.tick() == replace(expected, x=0x00CD, y=0x0001)


@cocotb.test()
@cocotb.parametrize(mask=[0x10, 0xFF])
async def setting_index_flag_clears_both_upper_bytes_on_the_same_edge(dut, mask):
    registers = await start_registers(dut)
    previous = await seed_index_state(registers)
    expected = replace(previous, p=masked_status(previous.p, 0xFF, mask), x=0x3C, y=0xC3)
    observed = await registers.cycle(p=0xFF, p_write=True, p_mask=mask)
    assert observed == expected, (
        "Setting P[4] must clear X/Y high bytes on this edge, without index writes: "
        f"expected {expected}, got {observed}"
    )
    assert await registers.cycle() == expected


@cocotb.test()
@cocotb.parametrize(status_request=[(False, 0xFF), (True, 0xEF), (True, 0x00)])
async def ignored_index_flag_changes_preserve_full_index_values(dut, status_request):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers)
    enabled, mask = status_request
    next_p = masked_status(expected.p, 0xFF, mask) if enabled else expected.p
    expected = replace(expected, p=next_p)
    assert await registers.cycle(p=0xFF, p_write=enabled, p_mask=mask) == expected
    assert await registers.cycle() == expected


@cocotb.test()
async def accumulator_width_bit_does_not_change_index_width(dut):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers)
    expected = replace(expected, p=0x20)
    assert await registers.cycle(p=0x20, p_write=True, p_mask=0x20) == expected
    assert await registers.cycle() == expected
    expected = replace(expected, x=0xFEDC, y=0x9876)
    assert await registers.cycle(x=0xFEDC, x16=True, y=0x9876, y16=True) == expected


@cocotb.test()
@cocotb.parametrize(register=["x", "y"])
async def stable_eight_bit_mode_truncates_even_full_index_write_requests(dut, register):
    # This is a defensive internal-interface contract, not a 16-bit CPU operation.
    registers = await start_registers(dut)
    expected = await seed_index_state(registers, index_flag=1)
    for value in (0x0000, 0x00FF, 0x0100, 0x8000, 0xABCD, 0xFFFF):
        expected = replace(expected, **{register: value % 256})
        assert await registers.cycle(**{register: value, f"{register}16": True}) == expected


@cocotb.test()
async def returning_to_sixteen_bit_mode_does_not_restore_discarded_bytes(dut):
    registers = await start_registers(dut)
    previous = await seed_index_state(registers)
    await registers.cycle(p=0x10, p_write=True, p_mask=0x10)
    # Same-edge clearing has its own test. Stabilize the narrow mode here to
    # independently check that returning to wide mode cannot restore old data.
    expected = replace(previous, p=0x10, x=0x3C, y=0xC3)
    assert await registers.cycle() == expected
    expected = replace(expected, p=0)
    assert await registers.cycle(p=0, p_write=True, p_mask=0x10) == expected
    assert await registers.cycle() == expected
    expected = replace(expected, x=0xABCD, y=0x1234)
    assert await registers.cycle(x=0xABCD, x16=True, y=0x1234, y16=True) == expected


@cocotb.test()
@cocotb.parametrize(target=["x", "y", "both"], write_width=[8, 16])
async def setting_index_flag_also_limits_simultaneous_index_writes(dut, target, write_width):
    registers = await start_registers(dut)
    previous = await seed_index_state(registers)
    inputs = dict(p=0x10, p_write=True, p_mask=0x10)
    expected = replace(previous, p=0x10, x=0x3C, y=0xC3)
    for register, value in (("x", 0x1357), ("y", 0x2468)):
        if target in (register, "both"):
            inputs.update({register: value, f"{register}{write_width}": True})
            expected = replace(expected, **{register: value % 256})
    observed = await registers.cycle(**inputs)
    assert observed == expected, (
        "Entering 8-bit mode must constrain both newly written and held indexes: "
        f"expected {expected}, got {observed}"
    )


@cocotb.test()
@cocotb.parametrize(target=["x", "y", "both"])
async def clearing_index_flag_allows_full_writes_on_the_same_edge(dut, target):
    registers = await start_registers(dut)
    expected = await seed_index_state(registers, index_flag=1)
    expected = replace(expected, p=0)
    inputs = dict(p=0, p_write=True, p_mask=0x10)
    for register, value in (("x", 0xABCD), ("y", 0x1234)):
        if target in (register, "both"):
            inputs.update({register: value, f"{register}16": True})
            expected = replace(expected, **{register: value})
    observed = await registers.cycle(**inputs)
    assert observed == expected, (
        "Leaving 8-bit mode must not discard the upper byte of a new 16-bit write: "
        f"expected {expected}, got {observed}"
    )


@cocotb.test()
@cocotb.parametrize(seed=[0x65816, 0x1D3E])
async def randomized_index_writes_and_mode_changes_match_reference_state(dut, seed):
    registers = await start_registers(dut)
    expected = RegisterState(0, 0, 0)
    rng = random.Random(seed)
    for index in range(1024):
        if index % 67 == 0:
            await registers.reset()
            await registers.enter_native()
            expected = RegisterState(0, 0, 0)

        inputs = dict(
            a=rng.randrange(65536), pc=rng.randrange(65536),
            pc_write=bool(rng.randrange(2)), pc_inc=bool(rng.randrange(2)),
            p=rng.randrange(256), p_write=bool(rng.randrange(2)),
            p_mask=rng.randrange(256), x=rng.randrange(65536), y=rng.randrange(65536),
        )
        writes = {}
        for register in ("a", "x", "y"):
            width = rng.choice((0, 8, 16))
            if width:
                inputs[f"{register}{width}"] = True
                writes[register] = width

        next_a = expected.a
        if writes.get("a") == 8:
            next_a = (expected.a // 256) * 256 + inputs["a"] % 256
        elif writes.get("a") == 16:
            next_a = inputs["a"]
        next_pc = (
            inputs["pc"] if inputs["pc_write"]
            else (expected.pc + int(inputs["pc_inc"])) % 65536
        )
        next_p = (
            masked_status(expected.p, inputs["p"], inputs["p_mask"])
            if inputs["p_write"] else expected.p
        )
        indexes = {}
        for register in ("x", "y"):
            value = inputs[register] if register in writes else getattr(expected, register)
            if writes.get(register) == 8 or next_p & 0x10:
                value %= 256
            indexes[register] = value

        expected = RegisterState(next_a, next_pc, next_p, **indexes)
        observed = await registers.cycle(**inputs)
        assert observed == expected, (
            f"seed={seed:#x}, update={index}, before/after mode applies to this edge, "
            f"inputs={inputs}: expected {expected}, got {observed}"
        )


@cocotb.test()
async def reset_selects_emulation_and_idle_inputs_cannot_change_it(dut):
    registers = await start_registers(dut, native=False)
    for value in (0, 1, 0, 1):
        assert await registers.cycle(e=value, p=0, p_mask=0xFF) == RESET_STATE


@cocotb.test()
@cocotb.parametrize(initial_e=[0, 1])
async def emulation_bit_only_changes_on_enabled_rising_edges(dut, initial_e):
    registers = await start_registers(dut, native=False)
    expected = replace(RESET_STATE, e=initial_e)
    if not initial_e:
        assert await registers.cycle(e=0, e_write=True) == expected

    assert await registers.cycle(e=1 - initial_e) == expected
    dut.clk_i.value = 0
    registers.drive(e=1 - initial_e, e_write=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    expected = replace(expected, e=1 - initial_e)
    assert await registers.tick() == expected

    registers.drive(e=initial_e, e_write=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    assert await registers.tick() == replace(expected, e=initial_e)


async def seed_native_mode(registers, status):
    await registers.cycle(p=status, p_write=True)
    expected = RegisterState(
        0xABCD, 0x4567, status,
        0x003C if status & 0x10 else 0xA53C,
        0x00C3 if status & 0x10 else 0x5AC3,
    )
    observed = await registers.cycle(
        a=expected.a, a16=True, pc=expected.pc, pc_write=True,
        x=expected.x, x16=True, y=expected.y, y16=True,
    )
    assert observed == expected
    return expected


@cocotb.test()
@cocotb.parametrize(mode_bits=[0x00, 0x10, 0x20, 0x30])
async def entering_emulation_forces_mode_bits_without_a_status_write(dut, mode_bits):
    registers = await start_registers(dut)
    previous = await seed_native_mode(registers, 0xC5 | mode_bits)
    expected = replace(previous, e=1, p=previous.p | 0x30,
                       x=previous.x % 256, y=previous.y % 256)
    observed = await registers.cycle(e=1, e_write=True)
    assert observed == expected, (
        "An E write must force M/X even with p_write_i=0, using the new E on this edge: "
        f"expected {expected}, got {observed}"
    )
    assert await registers.cycle(e=0) == expected


@cocotb.test()
@cocotb.parametrize(mask=[0x00, 0x10, 0x20, 0x30, 0xCF, 0xFF])
async def entering_emulation_overrides_a_simultaneous_masked_status_write(dut, mask):
    registers = await start_registers(dut)
    previous = await seed_native_mode(registers, 0xCF)
    expected = replace(previous, e=1, p=masked_status(previous.p, 0, mask) | 0x30,
                       x=0x3C, y=0xC3)
    assert await registers.cycle(e=1, e_write=True, p=0, p_write=True, p_mask=mask) == expected


@cocotb.test()
async def emulation_forces_mode_bits_for_every_status_mask(dut):
    registers = await start_registers(dut, native=False)
    base = RegisterState(0xABCD, 0x4567, 0x34, 0x3C, 0xC3, e=1)
    assert await registers.cycle(
        a=base.a, a16=True, pc=base.pc, pc_write=True,
        x=base.x, x8=True, y=base.y, y8=True,
    ) == base
    for previous in (0x30, 0xFF, 0x75, 0xBA):
        for value in (0x00, 0xFF, 0x3C, 0xC3):
            for mask in range(256):
                assert await registers.cycle(p=previous, p_write=True) == replace(
                    base, p=previous
                )
                expected = replace(base, p=masked_status(previous, value, mask) | 0x30)
                observed = await registers.cycle(
                    e=0, p=value, p_write=True, p_mask=mask,
                )
                assert observed == expected, (
                    f"E=1, P={previous:#04x}, data={value:#04x}, mask={mask:#04x}: "
                    f"expected {expected}, got {observed}"
                )


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def writing_status_including_carry_never_changes_the_emulation_bit(dut, emulation):
    registers = await start_registers(dut, native=False)
    if not emulation:
        await registers.cycle(e=0, e_write=True)
    for value in range(256):
        expected = RegisterState(0, 0, value | (0x30 if emulation else 0), e=emulation)
        assert await registers.cycle(e=1 - emulation, p=value, p_write=True) == expected


@cocotb.test()
async def leaving_emulation_keeps_mode_bits_until_a_later_status_write(dut):
    registers = await start_registers(dut, native=False)
    expected = RegisterState(0xABCD, 0x4567, 0xFF, 0x3C, 0xC3, e=1)
    assert await registers.cycle(
        a=expected.a, a16=True, pc=expected.pc, pc_write=True,
        p=0xFF, p_write=True, x=0x3C, x8=True, y=0xC3, y8=True,
    ) == expected
    expected = replace(expected, e=0)
    assert await registers.cycle(e=0, e_write=True) == expected
    assert await registers.cycle() == expected
    expected = replace(expected, p=0xCF)
    assert await registers.cycle(p=0, p_write=True, p_mask=0x30) == expected


@cocotb.test()
@cocotb.parametrize(target=["none", "x", "y", "both"])
async def leaving_emulation_allows_status_and_full_index_writes_on_the_same_edge(dut, target):
    registers = await start_registers(dut, native=False)
    previous = RegisterState(0xABCD, 0x4567, 0x34, 0x3C, 0xC3, e=1)
    assert await registers.cycle(
        a=previous.a, a16=True, pc=previous.pc, pc_write=True,
        x=0x3C, x8=True, y=0xC3, y8=True,
    ) == previous
    expected = replace(previous, e=0, p=0x04)
    inputs = dict(e=0, e_write=True, p=0, p_write=True, p_mask=0x30)
    for register, value in (("x", 0xFEDC), ("y", 0x9876)):
        if target in (register, "both"):
            inputs.update({register: value, f"{register}16": True})
            expected = replace(expected, **{register: value})
    observed = await registers.cycle(**inputs)
    assert observed == expected, (
        "E=0 and a cleared P[4] must allow the full index write on this edge: "
        f"expected {expected}, got {observed}"
    )


@cocotb.test()
@cocotb.parametrize(target=["x", "y", "both"], write_width=[8, 16])
async def entering_emulation_limits_simultaneous_index_writes(dut, target, write_width):
    registers = await start_registers(dut)
    previous = await seed_native_mode(registers, 0)
    expected = replace(previous, e=1, p=0x30, x=0x3C, y=0xC3)
    inputs = dict(e=1, e_write=True)
    for register, value in (("x", 0x1357), ("y", 0x2468)):
        if target in (register, "both"):
            inputs.update({register: value, f"{register}{write_width}": True})
            expected = replace(expected, **{register: value % 256})
    assert await registers.cycle(**inputs) == expected


@cocotb.test()
@cocotb.parametrize(mask=[0x00, 0x10, 0x20, 0x30])
async def leaving_emulation_only_clears_mode_bits_selected_by_the_status_mask(dut, mask):
    registers = await start_registers(dut, native=False)
    assert await registers.cycle(p=0xFF, p_write=True) == replace(RESET_STATE, p=0xFF)
    expected = RegisterState(0, 0, masked_status(0xFF, 0, mask))
    assert await registers.cycle(e=0, e_write=True, p=0, p_write=True, p_mask=mask) == expected


@cocotb.test()
async def mode_round_trip_keeps_accumulator_and_cannot_restore_discarded_index_bytes(dut):
    registers = await start_registers(dut)
    previous = await seed_native_mode(registers, 0)
    expected = replace(previous, e=1, p=0x30, x=0x3C, y=0xC3)
    assert await registers.cycle(e=1, e_write=True) == expected
    expected = replace(expected, e=0)
    assert await registers.cycle(e=0, e_write=True) == expected
    expected = replace(expected, p=0)
    assert await registers.cycle(p=0, p_write=True) == expected
    assert await registers.cycle() == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def reset_restores_emulation_even_with_pending_mode_and_status_writes(dut, emulation):
    registers = await start_registers(dut)
    await seed_native_mode(registers, 0xCF)
    if emulation:
        await registers.cycle(e=1, e_write=True)
    registers.drive(e=1 - emulation, e_write=True, p=0, p_write=True,
                    a=0xFFFF, a16=True, pc=0xFFFF, pc_write=True,
                    x=0xFFFF, x16=True, y=0xFFFF, y16=True)
    # reset() asserts and releases reset_ni without a clock edge in between.
    await registers.reset()
    assert registers.snapshot() == RESET_STATE
    assert await registers.cycle() == RESET_STATE


@cocotb.test()
@cocotb.parametrize(seed=[0xE65816, 0xE1])
async def randomized_mode_status_and_data_updates_match_reference_state(dut, seed):
    registers = await start_registers(dut, native=False)
    expected = RESET_STATE
    rng = random.Random(seed)
    transitions = set()
    for index in range(1024):
        if index % 79 == 0:
            await registers.reset()
            expected = RESET_STATE
        inputs = dict(
            e=rng.randrange(2), e_write=bool(rng.randrange(2)),
            a=rng.randrange(65536), pc=rng.randrange(65536),
            pc_write=bool(rng.randrange(2)), pc_inc=bool(rng.randrange(2)),
            p=rng.randrange(256), p_write=bool(rng.randrange(2)),
            p_mask=rng.randrange(256), x=rng.randrange(65536), y=rng.randrange(65536),
        )
        for register in ("a", "x", "y"):
            width = rng.choice((0, 8, 16))
            inputs[f"{register}8"] = width == 8
            inputs[f"{register}16"] = width == 16
        previous = expected
        expected = expected_mode_update(previous, inputs)
        if previous.e != expected.e:
            transitions.add((previous.e, expected.e))
        observed = await registers.cycle(**inputs)
        assert observed == expected, (
            f"seed={seed:#x}, update={index}, previous={previous}, inputs={inputs}: "
            f"expected {expected}, got {observed}"
        )
    assert transitions == {(0, 1), (1, 0)}, "random sequence must exercise both mode transitions"
