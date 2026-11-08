"""Stateful integration checks: register storage, operand routing and flag masks.

Operations are internal ALU commands, not instruction opcodes. Commands commit on
every asserted rising edge. ADC/SBC require D=0 until decimal arithmetic exists.
"""

import random
from dataclasses import dataclass

import cocotb
from cocotb.triggers import Timer


OPS = dict(ADD=0, SUB=1, ADC=2, SBC=3, AND=4, OR=5, XOR=6, ASL=7, LSR=8, ROL=9, ROR=10)
MODES = ["emulation", "native8", "native16"]


@dataclass(frozen=True)
class State:
    a: int = 0
    p: int = 0x34
    e: int = 1


def alu_reference(a, b, carry, width, operation):
    limit, sign = 1 << width, 1 << (width - 1)
    a, b = a % limit, b % limit
    signed_a = a if a < sign else a - limit
    signed_b = b if b < sign else b - limit
    c = v = 0
    if operation in (OPS["ADD"], OPS["ADC"]):
        extra = carry if operation == OPS["ADC"] else 0
        raw = a + b + extra
        c = int(raw >= limit)
        signed_result = signed_a + signed_b + extra
        v = int(not -sign <= signed_result < sign)
    elif operation in (OPS["SUB"], OPS["SBC"]):
        borrow = 1 - carry if operation == OPS["SBC"] else 0
        raw = a - b - borrow
        c = int(raw >= 0)
        signed_result = signed_a - signed_b - borrow
        v = int(not -sign <= signed_result < sign)
    elif operation == OPS["AND"]:
        raw = a & b
    elif operation == OPS["OR"]:
        raw = a | b
    elif operation == OPS["XOR"]:
        raw = a ^ b
    elif operation in (OPS["ASL"], OPS["ROL"]):
        raw = a * 2 + (carry if operation == OPS["ROL"] else 0)
        c = int(a >= sign)
    elif operation in (OPS["LSR"], OPS["ROR"]):
        raw = a // 2 + (carry * sign if operation == OPS["ROR"] else 0)
        c = a % 2
    else:
        raise AssertionError(f"unexpected reference operation {operation}")
    result = raw % limit
    flags = (int(result >= sign) << 7) | (v << 6) | (int(result == 0) << 1) | c
    mask = 0xC3 if operation <= OPS["SBC"] else 0x82 if operation <= OPS["XOR"] else 0x83
    return result, flags, mask


def next_state(state, *, operand=0, op=0, execute=False, load=False,
               p=0, p_mask=0xFF, p_write=False, e=0, e_write=False):
    width = 8 if state.p & 0x20 else 16
    new_a, new_p = state.a, state.p
    if execute:
        result, flags, mask = alu_reference(state.a, operand, state.p & 1, width, op)
    elif load:
        result = operand % (1 << width)
        flags = (int(result >= 1 << (width - 1)) << 7) | (int(result == 0) << 1)
        mask = 0x82
    elif p_write:
        new_p = (state.p & (0xFF ^ p_mask)) | (p & p_mask)
    if execute or load:
        new_a = result if width == 16 else (state.a // 256) * 256 + result
        new_p = (state.p & (0xFF ^ mask)) | (flags & mask)
    new_e = e if e_write else state.e
    if new_e:
        new_p |= 0x30
    return State(new_a, new_p, new_e)


class DatapathDriver:
    def __init__(self, dut):
        self.dut = dut

    def snapshot(self):
        return State(int(self.dut.a_out_o.value), int(self.dut.p_out_o.value),
                     int(self.dut.e_out_o.value))

    def drive(self, *, operand=0, op=0, execute=False, load=False,
              p=0, p_mask=0xFF, p_write=False, e=0, e_write=False):
        for name, value in dict(operand_i=operand, op_i=op, alu_exec_i=int(execute),
                                a_load_i=int(load), p_in_i=p, p_mask_i=p_mask,
                                p_write_i=int(p_write), e_in_i=e,
                                e_write_i=int(e_write)).items():
            getattr(self.dut, name).value = value

    async def reset(self):
        self.dut.reset_ni_i.value = 0
        await Timer(1, unit="ns")
        assert self.snapshot() == State(), "asynchronous datapath reset failed"
        self.dut.reset_ni_i.value = 1
        await Timer(1, unit="ns")

    async def start(self):
        self.dut.clk_i.value = 0
        self.dut.reset_ni_i.value = 1
        self.drive()
        await Timer(1, unit="ns")
        await self.reset()

    async def tick(self):
        self.dut.clk_i.value = 0
        await Timer(5, unit="ns")
        self.dut.clk_i.value = 1
        await Timer(5, unit="ns")
        return self.snapshot()

    async def cycle(self, **inputs):
        self.drive(**inputs)
        return await self.tick()

    async def seed(self, a, mode, flags=0):
        await self.cycle(e=0, e_write=True, p=0, p_write=True)
        await self.cycle(operand=a, load=True)
        emulation = int(mode == "emulation")
        status = flags | (0x20 if mode == "native8" else 0)
        if emulation:
            status |= 0x30
        expected = State(a, status, emulation)
        assert await self.cycle(e=emulation, e_write=True, p=status, p_write=True) == expected
        return expected


async def start_datapath(dut):
    driver = DatapathDriver(dut)
    await driver.start()
    return driver


@cocotb.test()
@cocotb.parametrize(mode=MODES, operation=list(OPS))
async def all_alu_commands_commit_results_and_only_their_flags(dut, mode, operation):
    driver = await start_datapath(dut)
    rng = random.Random(0xDADA + OPS[operation])
    pairs = [(0, 0), (0xFFFF, 1), (0x7FFF, 1), (0x80, 1), (0, 0xFFFF), (0x5555, 0xAAAA)]
    pairs += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(12)]
    for a, b in pairs:
        a = a if mode == "native16" else 0xAB00 | (a & 0xFF)
        previous = await driver.seed(a, mode, flags=rng.randrange(256) & ~0x28)
        inputs = dict(operand=b, op=OPS[operation], execute=True)
        expected = next_state(previous, **inputs)
        assert await driver.cycle(**inputs) == expected, (
            f"{mode} {operation}, before={previous}, operand={b:#06x}, expected={expected}"
        )


@cocotb.test()
@cocotb.parametrize(mode=MODES)
async def loading_accumulator_uses_mode_width_and_preserves_carry_overflow(dut, mode):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABCD, mode, flags=0x45)
    for value in (0, 1, 0x80, 0xFF, 0x0100, 0x8000, 0xFFFF):
        inputs = dict(operand=value, load=True)
        expected = next_state(expected, **inputs)
        assert await driver.cycle(**inputs) == expected


@cocotb.test()
@cocotb.parametrize(clock_level=[0, 1])
async def reset_is_asynchronous_and_overrides_conflicting_commands(dut, clock_level):
    driver = await start_datapath(dut)
    await driver.seed(0xABCD, "native16", flags=0xC5)
    dut.clk_i.value = clock_level
    await Timer(2, unit="ns")
    driver.drive(execute=True, load=True, p=0, p_write=True, e=0, e_write=True)
    dut.reset_ni_i.value = 0
    await Timer(1, unit="ns")
    assert driver.snapshot() == State()
    assert await driver.tick() == State()
    driver.drive()
    dut.reset_ni_i.value = 1
    assert await driver.tick() == State()


@cocotb.test()
async def inactive_commands_hold_state_even_with_an_invalid_idle_opcode(dut):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABCD, "native16", flags=0xC5)
    for value in range(128):
        assert await driver.cycle(operand=value * 257, op=0xFF, p=value,
                                  p_mask=value, e=value % 2) == expected


@cocotb.test()
async def accumulator_and_status_change_together_only_on_clock_edges(dut):
    driver = await start_datapath(dut)
    previous = await driver.seed(0xABFF, "native8")
    inputs = dict(operand=1, op=OPS["ADC"], execute=True)
    dut.clk_i.value = 0
    driver.drive(**inputs)
    await Timer(3, unit="ns")
    assert driver.snapshot() == previous
    expected = next_state(previous, **inputs)
    assert await driver.tick() == expected
    driver.drive(operand=0xFFFF, op=OPS["XOR"], execute=True)
    await Timer(3, unit="ns")
    assert driver.snapshot() == expected


@cocotb.test()
async def an_execute_enable_held_high_commits_on_every_rising_edge(dut):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABFE, "native8")
    inputs = dict(operand=1, op=OPS["ADC"], execute=True)
    driver.drive(**inputs)
    for _ in range(4):
        expected = next_state(expected, **inputs)
        assert await driver.tick() == expected
    assert await driver.cycle() == expected


@cocotb.test()
@cocotb.parametrize(emulation=[0, 1])
async def direct_status_path_respects_every_mask_and_mode_constraint(dut, emulation):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABCD, "emulation" if emulation else "native16")
    for mask in range(256):
        inputs = dict(p=mask ^ 0xA5, p_mask=mask, p_write=True, e=1 - emulation)
        expected = next_state(expected, **inputs)
        assert await driver.cycle(**inputs) == expected


@cocotb.test()
async def direct_emulation_and_status_writes_can_change_together(dut):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABCD, "native16")
    for inputs in (dict(e=1, e_write=True, p=0, p_write=True),
                   dict(e=0, e_write=True, p=0, p_write=True)):
        expected = next_state(expected, **inputs)
        assert await driver.cycle(**inputs) == expected


@cocotb.test()
async def eight_bit_adc_preserves_upper_accumulator_and_sets_carry_and_zero(dut):
    driver = await start_datapath(dut)
    await driver.seed(0xABFF, "native8")
    assert await driver.cycle(operand=1, op=OPS["ADC"], execute=True) == State(0xAB00, 0x23, 0)


@cocotb.test()
async def decimal_flag_is_preserved_by_load_and_logic_commands(dut):
    driver = await start_datapath(dut)
    expected = await driver.seed(0xABCD, "native8", flags=0x49)
    for inputs in (dict(operand=0x0F, op=OPS["AND"], execute=True),
                   dict(operand=0, load=True)):
        expected = next_state(expected, **inputs)
        assert await driver.cycle(**inputs) == expected


@cocotb.test()
@cocotb.parametrize(seed=[0x65816, 0xDA7A])
async def mixed_command_sequences_match_independent_state(dut, seed):
    driver = await start_datapath(dut)
    expected = State()
    rng = random.Random(seed)
    for index in range(512):
        if index % 61 == 0:
            await driver.reset()
            expected = State()
        command = rng.randrange(6)
        inputs = dict(operand=rng.randrange(65536), op=rng.randrange(11),
                      p=rng.randrange(256) & ~0x08, p_mask=rng.randrange(256),
                      e=rng.randrange(2))
        if command == 0:
            inputs["op"] = 0xFF
        elif command == 1:
            inputs["load"] = True
        elif command == 2:
            inputs["execute"] = True
        elif command == 3:
            inputs["p_write"] = True
        elif command == 4:
            inputs["e_write"] = True
        else:
            inputs.update(p_write=True, e_write=True)
        previous = expected
        expected = next_state(previous, **inputs)
        observed = await driver.cycle(**inputs)
        assert observed == expected, (
            f"seed={seed:#x}, update={index}, before={previous}, inputs={inputs}: "
            f"expected {expected}, got {observed}"
        )
