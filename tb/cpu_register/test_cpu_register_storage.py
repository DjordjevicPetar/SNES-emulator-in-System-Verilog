"""D/DBR/PBR/SP tests for the complete register block.

SP reset=01FF is a project choice. SP updates use reset > write > increment or
decrement, then constrain the high byte to 01 when the newly committed E is one.
Simultaneous increment/decrement is an invalid request, even with a direct write;
that case belongs to the separate assertion subprocess, not this legal suite.
"""

import random
from dataclasses import replace

import cocotb
from cocotb.triggers import Timer

from cpu_register_driver import CpuRegisterDriver
from cpu_register_model import RegisterState, RESET_STATE, expected_mode_update


async def start_storage(dut, emulation=0, status=0xC5):
    registers = CpuRegisterDriver(dut)
    await registers.start()
    if not emulation:
        await registers.enter_native()
    status = status | 0x30 if emulation else status
    await registers.cycle(p=status, p_write=True)
    expected = RegisterState(
        0xA5C3, 0x4567, status,
        0x0057 if status & 0x10 else 0x1357,
        0x00DF if status & 0x10 else 0x9BDF,
        e=emulation, d=0xBEEF, dbr=0xA6, pbr=0x5A,
        sp=0x01FE if emulation else 0xB7FE,
    )
    observed = await registers.cycle(
        a=expected.a, a16=True, pc=expected.pc, pc_write=True,
        x=expected.x, x16=True, y=expected.y, y16=True,
        d=expected.d, d_write=True, dbr=expected.dbr, dbr_write=True,
        pbr=expected.pbr, pbr_write=True, sp=expected.sp, sp_write=True,
    )
    assert observed == expected
    return registers, expected


def stack_value(value, emulation):
    return 0x0100 + value % 256 if emulation else value % 65536


@cocotb.test()
@cocotb.parametrize(register=["dbr", "pbr"], emulation=[0, 1])
async def bank_register_writes_store_every_byte_without_touching_other_state(
    dut, register, emulation
):
    registers, expected = await start_storage(dut, emulation)
    for value in range(256):
        expected = replace(expected, **{register: value})
        observed = await registers.cycle(**{register: value, f"{register}_write": True})
        assert observed == expected


@cocotb.test()
@cocotb.parametrize(mode=[(0, 0x00), (0, 0x10), (0, 0x20), (0, 0x30), (1, 0x30)])
async def direct_page_writes_always_store_all_sixteen_bits(dut, mode):
    emulation, bits = mode
    registers, expected = await start_storage(dut, emulation, 0xC5 | bits)
    values = (0x0000, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0xAAAA, 0x5555, 0xFFFF)
    values += tuple(1 << bit for bit in range(16))
    rng = random.Random(0xD16)
    values += tuple(rng.randrange(65536) for _ in range(128))
    for value in values:
        expected = replace(expected, d=value)
        assert await registers.cycle(d=value, d_write=True) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def storage_inputs_only_take_effect_at_a_rising_edge(dut, emulation):
    registers, expected = await start_storage(dut, emulation)
    dut.clk_i.value = 0
    registers.drive(d=0x1234, d_write=True, dbr=0x12, dbr_write=True,
                    pbr=0x34, pbr_write=True, sp=0x2345, sp_write=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    expected = replace(expected, d=0x1234, dbr=0x12, pbr=0x34,
                       sp=stack_value(0x2345, emulation))
    assert await registers.tick() == expected

    registers.drive(d=0xFFFF, d_write=True, dbr=0xFF, dbr_write=True,
                    pbr=0, pbr_write=True, sp=0xABCD, sp_write=True)
    await Timer(3, unit="ns")
    assert registers.snapshot() == expected
    assert await registers.tick() == replace(
        expected, d=0xFFFF, dbr=0xFF, pbr=0, sp=stack_value(0xABCD, emulation)
    )


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def disabled_storage_controls_hold_all_registers_despite_input_changes(dut, emulation):
    registers, expected = await start_storage(dut, emulation)
    rng = random.Random(0xD15AB1ED + emulation)
    for _ in range(128):
        assert await registers.cycle(
            d=rng.randrange(65536), dbr=rng.randrange(256), pbr=rng.randrange(256),
            sp=rng.randrange(65536), a=rng.randrange(65536), pc=rng.randrange(65536),
            x=rng.randrange(65536), y=rng.randrange(65536), e=1 - emulation,
            p=rng.randrange(256), p_mask=rng.randrange(256),
        ) == expected


@cocotb.test()
async def all_nine_registers_can_update_independently_on_the_same_edge(dut):
    registers, _ = await start_storage(dut)
    expected = RegisterState(0xBEEF, 0x8000, 0x05, 0x1234, 0x5678,
                             d=0xF123, dbr=0x7E, pbr=0x80, sp=0)
    assert await registers.cycle(
        e=0, e_write=True, a=expected.a, a16=True, pc=expected.pc, pc_write=True,
        p=expected.p, p_write=True, x=expected.x, x16=True, y=expected.y, y16=True,
        d=expected.d, d_write=True, dbr=expected.dbr, dbr_write=True,
        pbr=expected.pbr, pbr_write=True, sp=expected.sp, sp_write=True,
    ) == expected
    expected = replace(expected, e=1, a=0xBE34, pc=0x8001, p=0x35,
                       x=0x00CD, y=0x0078, dbr=0xA5, sp=0x0101)
    assert await registers.cycle(
        e=1, e_write=True, a=0x1234, a8=True, pc_inc=True,
        x=0xABCD, x16=True, y=0xFFFF, d=0, pbr=0,
        dbr=0xA5, dbr_write=True, sp_inc=True,
    ) == expected


@cocotb.test()
@cocotb.parametrize(bank=[0x00, 0x7E, 0x80, 0xFF])
async def pc_wrap_does_not_increment_the_program_bank(dut, bank):
    registers, expected = await start_storage(dut)
    expected = replace(expected, pc=0xFFFE, pbr=bank)
    assert await registers.cycle(pc=0xFFFE, pc_write=True, pbr=bank, pbr_write=True) == expected
    for value in (0xFFFF, 0x0000):
        expected = replace(expected, pc=value)
        assert await registers.cycle(pc_inc=True) == expected
    expected = replace(expected, pc=1, pbr=(bank + 1) % 256)
    assert await registers.cycle(pc_inc=True, pbr=expected.pbr, pbr_write=True) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def direct_page_register_and_decimal_flag_are_independent(dut, emulation):
    registers, expected = await start_storage(dut, emulation)
    expected = replace(expected, p=expected.p | 0x08)
    assert await registers.cycle(p=0x08, p_write=True, p_mask=0x08) == expected
    for value in (0x0000, 0xFFFF, 0x8000):
        expected = replace(expected, d=value)
        assert await registers.cycle(d=value, d_write=True) == expected
    expected = replace(expected, p=expected.p & ~0x08)
    assert await registers.cycle(p=0, p_write=True, p_mask=0x08) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def stack_writes_store_full_values_or_force_page_one(dut, emulation):
    registers, expected = await start_storage(dut, emulation)
    values = (0, 0x00FF, 0x0100, 0x01FF, 0x0200, 0x7FFF, 0x8000, 0xABCD, 0xFFFF)
    values += tuple(1 << bit for bit in range(16))
    for value in values:
        expected = replace(expected, sp=stack_value(value, emulation))
        assert await registers.cycle(sp=value, sp_write=True) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1], direction=[-1, 1])
async def stack_moves_wrap_at_the_correct_boundary_and_preserve_flags(dut, emulation, direction):
    registers, expected = await start_storage(dut, emulation)
    for value in (0, 1, 0x00FF, 0x0100, 0x01FF, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
        expected = replace(expected, sp=stack_value(value, emulation))
        assert await registers.cycle(sp=value, sp_write=True) == expected
        expected = replace(expected, sp=stack_value(expected.sp + direction, emulation))
        assert await registers.cycle(sp_inc=direction == 1, sp_dec=direction == -1) == expected
        assert await registers.cycle(sp=0xAAAA) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1], direction=[-1, 1])
async def direct_stack_write_has_priority_over_movement(dut, emulation, direction):
    registers, expected = await start_storage(dut, emulation)
    for value in (0, 0x00FF, 0x0100, 0xABCD, 0xFFFF):
        expected = replace(expected, sp=stack_value(value, emulation))
        assert await registers.cycle(
            sp=value, sp_write=True, sp_inc=direction == 1, sp_dec=direction == -1,
        ) == expected


@cocotb.test()
@cocotb.parametrize(direction=[-1, 1])
async def emulation_stack_visits_every_byte_and_wraps_within_page_one(dut, direction):
    registers, expected = await start_storage(dut, emulation=1)
    initial = 0 if direction == 1 else 0xFF
    expected = replace(expected, sp=0x0100 + initial)
    assert await registers.cycle(sp=expected.sp, sp_write=True) == expected
    for step in range(1, 257):
        expected = replace(expected, sp=0x0100 + (initial + direction * step) % 256)
        assert await registers.cycle(sp_inc=direction == 1, sp_dec=direction == -1) == expected


@cocotb.test()
@cocotb.parametrize(mode_bits=[0x00, 0x10, 0x20, 0x30])
async def native_stack_width_is_independent_of_accumulator_and_index_width(dut, mode_bits):
    registers, expected = await start_storage(dut, status=0xC5 | mode_bits)
    expected = replace(expected, sp=0xBEEF)
    assert await registers.cycle(sp=0xBEEF, sp_write=True) == expected
    expected = replace(expected, sp=0xBEF0)
    assert await registers.cycle(sp_inc=True) == expected


@cocotb.test()
@cocotb.parametrize(value=[0x0000, 0xFFFF, 0xABCD, 0x1200, 0x01EF])
async def entering_emulation_constrains_stack_without_a_stack_write(dut, value):
    registers, expected = await start_storage(dut)
    expected = replace(expected, sp=value)
    assert await registers.cycle(sp=value, sp_write=True) == expected
    expected = replace(expected, e=1, p=expected.p | 0x30,
                       x=expected.x % 256, y=expected.y % 256,
                       sp=0x0100 + value % 256)
    assert await registers.cycle(e=1, e_write=True) == expected


@cocotb.test()
@cocotb.parametrize(new_e=[0, 1], action=["hold", "write", "increment", "decrement"])
async def stack_update_uses_new_emulation_mode_on_the_same_edge(dut, new_e, action):
    registers, expected = await start_storage(dut, emulation=1 - new_e)
    initial = {
        "hold": 0xABEF if new_e else 0x01EF,
        "write": 0x12FE if new_e else 0x01FE,
        "increment": 0x12FF if new_e else 0x01FF,
        "decrement": 0x1200 if new_e else 0x0100,
    }[action]
    expected = replace(expected, sp=initial)
    assert await registers.cycle(sp=initial, sp_write=True) == expected
    inputs = dict(e=new_e, e_write=True)
    result = initial
    if action == "write":
        inputs.update(sp=0xABCD, sp_write=True)
        result = 0xABCD
    elif action == "increment":
        inputs["sp_inc"] = True
        result += 1
    elif action == "decrement":
        inputs["sp_dec"] = True
        result -= 1
    status = expected.p | 0x30 if new_e else expected.p
    expected = replace(expected, e=new_e, p=status, sp=stack_value(result, new_e),
                       x=expected.x % 256 if status & 0x10 else expected.x,
                       y=expected.y % 256 if status & 0x10 else expected.y)
    assert await registers.cycle(**inputs) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def disabled_emulation_writes_cannot_change_stack_width(dut, emulation):
    registers, expected = await start_storage(dut, emulation)
    expected = replace(expected, sp=stack_value(0xABCD, emulation))
    assert await registers.cycle(e=1 - emulation, sp=0xABCD, sp_write=True) == expected
    for _ in range(4):
        assert await registers.cycle(e=1 - emulation) == expected


@cocotb.test()
async def stack_round_trip_does_not_restore_the_discarded_native_high_byte(dut):
    registers, expected = await start_storage(dut)
    expected = replace(expected, sp=0xABCD)
    assert await registers.cycle(sp=0xABCD, sp_write=True) == expected
    expected = replace(expected, e=1, p=expected.p | 0x30,
                       x=expected.x % 256, y=expected.y % 256, sp=0x01CD)
    assert await registers.cycle(e=1, e_write=True) == expected
    expected = replace(expected, e=0)
    assert await registers.cycle(e=0, e_write=True) == expected
    expected = replace(expected, sp=0xBEEF)
    assert await registers.cycle(sp=0xBEEF, sp_write=True) == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1], clock_level=[0, 1])
async def reset_initializes_all_storage_without_clock_even_with_conflicting_controls(
    dut, emulation, clock_level
):
    registers, _ = await start_storage(dut, emulation)
    dut.clk_i.value = clock_level
    await Timer(2, unit="ns")
    registers.drive(
        a=0xFFFF, a8=True, a16=True, x=0xFFFF, x8=True, x16=True,
        y=0xFFFF, y8=True, y16=True, e=1 - emulation, e_write=True,
        p=0, p_write=True, pc=0xFFFF, pc_write=True, pc_inc=True,
        d=0xFFFF, d_write=True, dbr=0xFF, dbr_write=True,
        pbr=0xFF, pbr_write=True, sp=0xFFFF, sp_write=True, sp_inc=True, sp_dec=True,
    )
    await registers.reset()
    assert registers.snapshot() == RESET_STATE
    assert await registers.cycle() == RESET_STATE


@cocotb.test()
@cocotb.parametrize(seed=[0x65816D, 0x5A6B])
async def randomized_complete_register_updates_match_independent_state(dut, seed):
    registers = CpuRegisterDriver(dut)
    await registers.start()
    expected = RESET_STATE
    rng = random.Random(seed)
    for index in range(1536):
        if index % 127 == 0:
            await registers.reset()
            expected = RESET_STATE
        movement = rng.choice((-1, 0, 1))
        inputs = dict(
            e=rng.randrange(2), e_write=bool(rng.randrange(2)),
            a=rng.randrange(65536), pc=rng.randrange(65536),
            pc_write=bool(rng.randrange(2)), pc_inc=bool(rng.randrange(2)),
            p=rng.randrange(256), p_write=bool(rng.randrange(2)), p_mask=rng.randrange(256),
            x=rng.randrange(65536), y=rng.randrange(65536),
            d=rng.randrange(65536), d_write=bool(rng.randrange(2)),
            dbr=rng.randrange(256), dbr_write=bool(rng.randrange(2)),
            pbr=rng.randrange(256), pbr_write=bool(rng.randrange(2)),
            sp=rng.randrange(65536), sp_write=bool(rng.randrange(2)),
            sp_inc=movement == 1, sp_dec=movement == -1,
        )
        for register in ("a", "x", "y"):
            width = rng.choice((0, 8, 16))
            inputs[f"{register}8"] = width == 8
            inputs[f"{register}16"] = width == 16
        previous = expected
        expected = expected_mode_update(previous, inputs)
        observed = await registers.cycle(**inputs)
        assert observed == expected, (
            f"seed={seed:#x}, update={index}, previous={previous}, inputs={inputs}: "
            f"expected {expected}, got {observed}"
        )
