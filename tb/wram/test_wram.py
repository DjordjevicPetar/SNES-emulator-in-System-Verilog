import random

import cocotb

from wram_driver import WMDATA, WMADDH, WMADDL, WMADDM, WramDriver
from wram_model import WramModel


async def start_wram(dut):
    driver = WramDriver(dut)
    await driver.start()
    return driver


@cocotb.test()
async def reset_releases_bus_resets_wm_address_and_preserves_memory(dut):
    wram = await start_wram(dut)

    assert int(dut.data_bus_oe_o.value) == 0

    await wram.a_write(0x00000, 0x5A)
    await wram.wm_set_address(0x12345)
    await wram.reset()

    assert await wram.a_read(0x00000) == 0x5A
    assert await wram.wm_read() == 0x5A


@cocotb.test()
async def a_bus_accesses_full_128k_address_space(dut):
    wram = await start_wram(dut)
    samples = {
        0x00000: 0x10,
        0x00001: 0x21,
        0x01FFF: 0x32,
        0x02000: 0x43,
        0x0FFFF: 0x54,
        0x10000: 0x65,
        0x1FFFF: 0x76,
    }

    for address, expected in samples.items():
        observation = await wram.a_write(address, expected)
        assert not observation.output_enabled

    for address, expected in samples.items():
        assert await wram.a_read(address) == expected


@cocotb.test()
async def a_bus_low_ram_mode_mirrors_every_8k(dut):
    wram = await start_wram(dut)

    await wram.a_write(0x00123, 0xA5)
    for mirrored_address in (0x00123, 0x02123, 0x10123, 0x1E123):
        assert await wram.a_read(mirrored_address, full_address=False) == 0xA5

    await wram.a_write(0x1E456, 0x5A, full_address=False)
    assert await wram.a_read(0x00456) == 0x5A


@cocotb.test()
async def a_bus_ignores_cycles_when_ram_is_not_selected(dut):
    wram = await start_wram(dut)
    address = 0x12345

    await wram.a_write(address, 0x11)
    ignored_write = await wram.a_write(address, 0xEE, selected=False)

    assert not ignored_write.output_enabled
    assert await wram.a_read(address) == 0x11

    ignored_read = await wram.a_read_cycle(address, selected=False)
    assert not ignored_read.output_enabled
    assert ignored_read.data is None


@cocotb.test()
async def wm_address_registers_form_a_17_bit_address(dut):
    wram = await start_wram(dut)
    samples = {
        0x000A5: 0x11,
        0x05A00: 0x22,
        0x10000: 0x33,
        0x1A2B3: 0x44,
    }

    for address, expected in samples.items():
        register_writes = (
            await wram.b_write_register(WMADDL, address & 0xFF),
            await wram.b_write_register(WMADDM, (address >> 8) & 0xFF),
            await wram.b_write_register(WMADDH, (address >> 16) & 0x01),
        )
        assert all(not result.output_enabled for result in register_writes)

        wmdata_write = await wram.wm_write(expected)
        assert not wmdata_write.output_enabled

    for address, expected in samples.items():
        assert await wram.a_read(address) == expected


@cocotb.test()
async def wmaddh_uses_only_bit_zero(dut):
    wram = await start_wram(dut)

    await wram.b_write_register(WMADDL, 0x00)
    await wram.b_write_register(WMADDM, 0x00)
    await wram.b_write_register(WMADDH, 0xFE)
    await wram.wm_write(0x12)

    await wram.b_write_register(WMADDL, 0x00)
    await wram.b_write_register(WMADDM, 0x00)
    await wram.b_write_register(WMADDH, 0xFF)
    await wram.wm_write(0x34)

    assert await wram.a_read(0x00000) == 0x12
    assert await wram.a_read(0x10000) == 0x34


@cocotb.test()
async def wmdata_writes_increment_and_wrap_the_address(dut):
    wram = await start_wram(dut)
    values = (0xA1, 0xB2, 0xC3)
    expected_addresses = (0x1FFFE, 0x1FFFF, 0x00000)

    await wram.wm_set_address(0x1FFFE)
    for value in values:
        observation = await wram.wm_write(value)
        assert not observation.output_enabled

    for address, expected in zip(expected_addresses, values):
        assert await wram.a_read(address) == expected


@cocotb.test()
async def wmdata_reads_increment_and_wrap_the_address(dut):
    wram = await start_wram(dut)
    addresses = (0x1FFFE, 0x1FFFF, 0x00000)
    values = (0x1A, 0x2B, 0x3C)

    for address, value in zip(addresses, values):
        await wram.a_write(address, value)

    await wram.wm_set_address(0x1FFFE)
    observed = tuple([await wram.wm_read() for _ in values])

    assert observed == values


@cocotb.test()
async def write_only_and_unused_b_bus_reads_are_open_bus(dut):
    wram = await start_wram(dut)

    await wram.a_write(0x00000, 0xD7)
    await wram.wm_set_address(0x00000)
    valid_read = await wram.b_read_register(WMDATA)
    assert valid_read.output_enabled
    assert valid_read.data == 0xD7

    await wram.a_write(0x00040, 0x4D)
    await wram.wm_set_address(0x00040)
    for register in (WMADDL, WMADDM, WMADDH, 0x84, 0xA0, 0xFF):
        observation = await wram.b_read_register(register)
        assert not observation.output_enabled
        assert observation.data is None

    assert await wram.wm_read() == 0x4D


@cocotb.test()
async def unused_b_bus_writes_have_no_side_effects(dut):
    wram = await start_wram(dut)
    target_address = 0x03456

    await wram.wm_set_address(target_address)
    for register in (0x84, 0xA0, 0xFF):
        observation = await wram.b_write_register(register, 0xEE)
        assert not observation.output_enabled

    await wram.wm_write(0xA5)
    assert await wram.a_read(target_address) == 0xA5


@cocotb.test()
async def randomized_cross_port_accesses_match_reference_model(dut):
    wram = await start_wram(dut)
    model = WramModel()
    rng = random.Random(0x65816)

    for _ in range(48):
        address = rng.randrange(WramModel.SIZE)
        value = rng.randrange(0x100)
        operation = rng.randrange(3)

        if operation == 0:
            await wram.a_write(address, value)
            model.a_write(address, value)

            await wram.wm_set_address(address)
            model.wm_set_address(address)
            assert await wram.wm_read() == model.wm_read()

        elif operation == 1:
            await wram.wm_set_address(address)
            model.wm_set_address(address)
            await wram.wm_write(value)
            model.wm_write(value)

            assert await wram.a_read(address) == model.a_read(address)

        else:
            await wram.a_write(address, value, full_address=False)
            model.a_write(address, value, full_address=False)

            mirrored_address = model.a_effective_address(address, False)
            assert await wram.a_read(mirrored_address) == model.a_read(
                mirrored_address
            )
