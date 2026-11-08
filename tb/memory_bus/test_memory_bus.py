"""Integration tests for the current WRAM-only memory bus.

    CPU address -> mapper -> actual WRAM -> CPU read data / ready

These tests do not check SNES access speeds, refresh stalls, or ROM/SRAM/I/O
data transfers: those are not implemented yet. The explicitly named placeholder
test records their CURRENT zero-response contract, not real SNES open bus.
"""

import random

import cocotb

from memory_bus_driver import MemoryBusDriver


MAP_MODES = (0, 1, 2)
SYSTEM_BANKS = tuple(range(0x40)) + tuple(range(0x80, 0xC0))


async def start_bus(dut, map_mode=0):
    bus = MemoryBusDriver(dut, map_mode)
    await bus.start()
    return bus


def full_wram_address(physical_address):
    return 0x7E0000 + physical_address


def cpu_alias(physical_address, rng):
    if physical_address < 0x2000 and rng.randrange(2):
        return (rng.choice(SYSTEM_BANKS) << 16) | physical_address
    return full_wram_address(physical_address)


@cocotb.test()
@cocotb.parametrize(map_mode=MAP_MODES)
async def full_wram_addresses_and_bank_boundaries_are_independent(dut, map_mode):
    bus = await start_bus(dut, map_mode)
    addresses = (
        0x00000, 0x00001, 0x00123, 0x01FFF, 0x02000, 0x03FFF,
        0x07FFF, 0x08000, 0x0FFFF, 0x10000, 0x10001, 0x1FFFF,
    )
    expected = {address: (index * 19 + 7) & 0xFF for index, address in enumerate(addresses)}

    # Write all locations before reading any: aliasing must not pass unnoticed.
    for address, value in expected.items():
        await bus.write(full_wram_address(address), value)
    for address, value in expected.items():
        assert await bus.read(full_wram_address(address)) == value, (
            f"WRAM address {address:#07x} did not retain its own value"
        )


@cocotb.test()
@cocotb.parametrize(map_mode=MAP_MODES)
async def low_wram_mirrors_support_reads_and_writes_in_every_system_bank(dut, map_mode):
    bus = await start_bus(dut, map_mode)
    for offset in (0x0000, 0x0123, 0x1FFF):
        expected = 0xA5
        await bus.write(full_wram_address(offset), expected)
        for bank in SYSTEM_BANKS:
            address = (bank << 16) | offset
            assert await bus.read(address) == expected, f"bad mirror at {address:#08x}"
            expected = (expected + 17) & 0xFF
            await bus.write(address, expected)
            assert await bus.read(full_wram_address(offset)) == expected


@cocotb.test()
@cocotb.parametrize(write=[False, True])
async def held_request_generates_one_ack_and_one_wram_access(dut, write):
    bus = await start_bus(dut)
    address = 0x7E1234
    await bus.write(address, 0x3C)
    before_reads, before_writes = bus.wram_reads, bus.wram_writes
    result = await bus.transfer(address, write=write, data=0xA5, hold_cycles=20)

    assert result.latency_cycles == 1, "current WRAM response must follow its accepting edge"
    if write:
        assert bus.wram_writes - before_writes == 1, "one request wrote WRAM repeatedly"
        assert bus.wram_reads - before_reads == 0
        assert await bus.read(address) == 0xA5
    else:
        assert result.data == 0x3C
        assert bus.wram_reads - before_reads == 1, "one request read WRAM repeatedly"
        assert bus.wram_writes - before_writes == 0


@cocotb.test()
async def idle_address_and_write_signal_changes_have_no_side_effects(dut):
    bus = await start_bus(dut)
    expected = {0x7E0000: 0x11, 0x7E1FFF: 0x22, 0x7F0000: 0x33, 0x7FFFFF: 0x44}
    for address, value in expected.items():
        await bus.write(address, value)

    before_reads, before_writes = bus.wram_reads, bus.wram_writes
    rng = random.Random(0x1D1E)
    for _ in range(80):
        dut.req_i.value = 0
        dut.addr_i.value = rng.choice(tuple(expected))
        dut.wr_i.value = rng.randrange(2)
        dut.wr_data_i.value = rng.randrange(256)
        dut.map_mode_i.value = rng.choice(MAP_MODES)
        assert not (await bus.cycle()).ready
    assert bus.wram_reads == before_reads
    assert bus.wram_writes == before_writes

    for address, value in expected.items():
        assert await bus.read(address) == value


@cocotb.test()
async def one_low_request_cycle_rearms_the_bus(dut):
    bus = await start_bus(dut)
    before_ready = bus.ready_cycles
    for index in range(24):
        address = 0x7E0100 + index
        value = (index * 11) & 0xFF
        await bus.write(address, value, hold_cycles=index % 3)
        assert await bus.read(address, hold_cycles=index % 5) == value
    assert bus.ready_cycles - before_ready == 48


@cocotb.test()
@cocotb.parametrize(held_cycles=[0, 3])
async def reset_releases_completed_or_held_request_and_preserves_wram(dut, held_cycles):
    bus = await start_bus(dut)
    address = 0x7E0456
    await bus.write(address, 0xA7)
    bus.drive_request(address)
    completed = await bus.cycle()
    assert completed.ready and completed.data == 0xA7
    for _ in range(held_cycles):
        assert not (await bus.cycle()).ready

    # Reset while ready is high or while a completed request is still held.
    await bus.reset()
    assert await bus.read(address) == 0xA7
    await bus.write(address, 0x5B)
    assert await bus.read(address) == 0x5B


@cocotb.test()
async def reset_before_accepting_edge_cancels_write(dut):
    bus = await start_bus(dut)
    address = 0x7E0678
    await bus.write(address, 0x2D)
    before_writes = bus.wram_writes
    bus.drive_request(address, write=True, data=0xEE)
    # No accepting clock edge occurs between issuing the request and reset.
    await bus.reset()
    assert bus.wram_writes == before_writes
    assert await bus.read(address) == 0x2D


@cocotb.test()
@cocotb.parametrize(map_mode=MAP_MODES)
async def unimplemented_targets_return_placeholder_zero_without_touching_wram(dut, map_mode):
    bus = await start_bus(dut, map_mode)
    expected = {0x7E0000: 0xA1, 0x7E0180: 0xB2, 0x7E1234: 0xC3, 0x7F6000: 0xD4}
    for address, value in expected.items():
        await bus.write(address, value)
    before_reads, before_writes = bus.wram_reads, bus.wram_writes

    for address in (
        0x002000, 0x002180, 0x002181, 0x002183, 0x005FFF,
        0x006000, 0x007FFF, 0x008000, 0x00FFFC, 0xB06000, 0xC01234,
    ):
        await bus.write(address, 0xEE, hold_cycles=2)
        assert await bus.read(address, hold_cycles=2) == 0, (
            f"WRAM-only bus placeholder response changed at {address:#08x}"
        )
    assert bus.wram_reads == before_reads
    assert bus.wram_writes == before_writes
    for address, value in expected.items():
        assert await bus.read(address) == value


@cocotb.test()
async def switching_mapper_does_not_change_console_wram(dut):
    bus = await start_bus(dut)
    await bus.write(0x7E0123, 0x8B)
    await bus.write(0x7F0123, 0xC7)
    for map_mode in (0, 1, 2, 3, 2, 1, 0):
        # Mode 3 disables cartridge mapping, but console WRAM remains available.
        dut.map_mode_i.value = map_mode
        assert await bus.read(0x000123) == 0x8B
        assert await bus.read(0x7F0123) == 0xC7


@cocotb.test()
@cocotb.parametrize(map_mode=MAP_MODES)
async def randomized_transactions_match_reference_memory(dut, map_mode):
    bus = await start_bus(dut, map_mode)
    rng = random.Random(0x65816 + map_mode)
    addresses = {0, 1, 0x1FFF, 0x2000, 0xFFFF, 0x10000, 0x1FFFF}
    addresses.update(rng.randrange(0x2000) for _ in range(16))
    addresses.update(rng.randrange(0x20000) for _ in range(24))
    addresses = sorted(addresses)
    model = {}

    # Initialize through the public bus; never assume power-up RAM contents.
    for physical in addresses:
        value = rng.randrange(256)
        await bus.write(full_wram_address(physical), value)
        model[physical] = value

    for _ in range(240):
        physical = rng.choice(addresses)
        address = cpu_alias(physical, rng)
        held_cycles = rng.randrange(6)
        if rng.randrange(2):
            value = rng.randrange(256)
            await bus.write(address, value, hold_cycles=held_cycles)
            model[physical] = value
        else:
            observed = await bus.read(address, hold_cycles=held_cycles)
            assert observed == model[physical], (
                f"mode={map_mode}, CPU={address:#08x}, WRAM={physical:#07x}: "
                f"expected {model[physical]:#04x}, got {observed:#04x}"
            )
        await bus.idle(rng.randrange(3))

    for physical, expected in model.items():
        assert await bus.read(full_wram_address(physical)) == expected
