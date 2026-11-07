import cocotb
from cocotb.triggers import Timer


MAP_LOROM = 0
MAP_HIROM = 1
MAP_EXHIROM = 2
ALL_MAP_MODES = (MAP_LOROM, MAP_HIROM, MAP_EXHIROM)

TARGETS = ("wram", "io", "sram", "rom")
ADDRESS_OUTPUTS = {
    "wram": "wram_address",
    "io": "io_address",
    "sram": "sram_address",
    "rom": "rom_address",
}


def cpu_address(bank, offset):
    return (bank << 16) | offset


def reference_decode(map_mode, address):
    bank = (address >> 16) & 0xFF
    offset = address & 0xFFFF
    system_bank = bank < 0x40 or 0x80 <= bank < 0xC0

    if bank in (0x7E, 0x7F):
        return "wram", ((bank & 1) << 16) | offset

    if system_bank and offset < 0x2000:
        return "wram", offset

    if system_bank and 0x2000 <= offset < 0x6000:
        return "io", offset

    if map_mode == MAP_LOROM:
        in_sram_bank = 0x70 <= bank < 0x7E or bank >= 0xF0
        if in_sram_bank and offset < 0x8000:
            return "sram", ((bank & 0x0F) << 15) | (offset & 0x7FFF)

        in_upper_rom = (bank < 0x7E or bank >= 0x80) and offset >= 0x8000
        in_lower_rom = (
            0x40 <= bank < 0x70 or 0xC0 <= bank < 0xF0
        ) and offset < 0x8000
        if in_upper_rom or in_lower_rom:
            return "rom", ((bank & 0x7F) << 15) | (offset & 0x7FFF)

    elif map_mode == MAP_HIROM:
        in_sram_bank = 0x30 <= bank < 0x40 or 0xB0 <= bank < 0xC0
        if in_sram_bank and 0x6000 <= offset < 0x8000:
            return "sram", ((bank & 0x0F) << 13) | (offset & 0x1FFF)

        in_upper_rom = (bank < 0x7E or bank >= 0x80) and offset >= 0x8000
        in_full_rom_bank = 0x40 <= bank < 0x7E or bank >= 0xC0
        if in_upper_rom or (in_full_rom_bank and offset < 0x8000):
            return "rom", ((bank & 0x3F) << 16) | offset

    elif map_mode == MAP_EXHIROM:
        if 0xB0 <= bank < 0xC0 and 0x6000 <= offset < 0x8000:
            return "sram", ((bank & 0x0F) << 13) | (offset & 0x1FFF)

        in_upper_rom = (bank < 0x7E or bank >= 0x80) and offset >= 0x8000
        in_full_rom_bank = 0x40 <= bank < 0x7E or bank >= 0xC0
        if in_upper_rom or (in_full_rom_bank and offset < 0x8000):
            upper_rom_bit = 0 if bank >= 0x80 else 1
            rom_address = (
                (upper_rom_bit << 22) | ((bank & 0x3F) << 16) | offset
            )
            return "rom", rom_address

    return None, None


async def decode(dut, map_mode, address):
    dut.map_mode_i.value = map_mode
    dut.addr_i.value = address
    await Timer(1, unit="ns")

    result = {
        "wram_selected": bool(int(dut.wram_sel_o.value)),
        "wram_address": int(dut.wram_addr_o.value),
        "io_selected": bool(int(dut.io_sel_o.value)),
        "io_address": int(dut.io_addr_o.value),
        "sram_selected": bool(int(dut.sram_sel_o.value)),
        "sram_address": int(dut.sram_addr_o.value),
        "rom_selected": bool(int(dut.rom_sel_o.value)),
        "rom_address": int(dut.rom_addr_o.value),
    }

    selected_targets = {
        target for target in TARGETS if result[f"{target}_selected"]
    }
    assert len(selected_targets) <= 1, (
        f"mode {map_mode}, address {address:#08x}: "
        f"multiple targets selected: {selected_targets}"
    )
    return result


def assert_target(result, expected_target, expected_address, map_mode, address):
    selected_targets = {
        target for target in TARGETS if result[f"{target}_selected"]
    }
    expected_targets = set() if expected_target is None else {expected_target}

    assert selected_targets == expected_targets, (
        f"mode {map_mode}, address {address:#08x}: "
        f"expected {expected_targets or {'open_bus'}}, "
        f"selected {selected_targets or {'open_bus'}}"
    )

    if expected_target is not None:
        output_name = ADDRESS_OUTPUTS[expected_target]
        assert result[output_name] == expected_address, (
            f"mode {map_mode}, address {address:#08x}: "
            f"expected {expected_target} address {expected_address:#07x}, "
            f"got {result[output_name]:#07x}"
        )


async def assert_matches_reference(dut, map_mode, address):
    expected_target, expected_address = reference_decode(map_mode, address)
    result = await decode(dut, map_mode, address)
    assert_target(result, expected_target, expected_address, map_mode, address)


@cocotb.test()
async def interface_has_common_widths_for_every_mapper(dut):
    assert len(dut.map_mode_i) == 2
    assert len(dut.addr_i) == 24
    assert len(dut.wram_addr_o) == 17
    assert len(dut.sram_addr_o) == 19
    assert len(dut.rom_addr_o) == 23


@cocotb.test()
async def console_wram_and_io_map_is_shared_by_all_modes(dut):
    samples = (
        0x000000,
        0x001FFF,
        0x002000,
        0x005FFF,
        0x3F0123,
        0x802345,
        0xBF5FFF,
        0x7E0000,
        0x7EFFFF,
        0x7F0000,
        0x7FFFFF,
    )

    for map_mode in ALL_MAP_MODES:
        for address in samples:
            await assert_matches_reference(dut, map_mode, address)


@cocotb.test()
async def lorom_maps_32k_rom_banks_and_linear_sram(dut):
    samples = (
        0x008000,
        0x00FFFF,
        0x408000,
        0x400000,
        0xC00000,
        0xEFFFFF,
        0x700000,
        0x707FFF,
        0x710000,
        0x7D7FFF,
        0xF00000,
        0xFF7FFF,
        0x006000,
        0x807FFF,
    )

    for address in samples:
        await assert_matches_reference(dut, MAP_LOROM, address)


@cocotb.test()
async def hirom_maps_64k_rom_banks_and_both_sram_windows(dut):
    samples = (
        0x008000,
        0x00FFFF,
        0x400000,
        0x7DFFFF,
        0xC00000,
        0xFFFFFF,
        0x306000,
        0x307FFF,
        0x316000,
        0x3F7FFF,
        0xB06000,
        0xBF7FFF,
        0x206000,
        0xAF7FFF,
    )

    for address in samples:
        await assert_matches_reference(dut, MAP_HIROM, address)


@cocotb.test()
async def exhirom_selects_both_rom_halves_and_mode25_sram(dut):
    samples = (
        0xC00000,
        0xFFFFFF,
        0x400000,
        0x7DFFFF,
        0x008000,
        0x3DFFFF,
        0x3E8000,
        0x3FFFFF,
        0xB06000,
        0xB07FFF,
        0xB16000,
        0xBF7FFF,
        0x306000,
        0x3F7FFF,
    )

    for address in samples:
        await assert_matches_reference(dut, MAP_EXHIROM, address)


@cocotb.test()
async def switching_map_mode_changes_only_cartridge_decoding(dut):
    address = 0x008000
    expected_rom_addresses = {
        MAP_LOROM: 0x000000,
        MAP_HIROM: 0x008000,
        MAP_EXHIROM: 0x408000,
    }

    for map_mode, expected_rom_address in expected_rom_addresses.items():
        result = await decode(dut, map_mode, address)
        assert_target(result, "rom", expected_rom_address, map_mode, address)

    shared_wram_address = 0x000123
    observations = []
    for map_mode in ALL_MAP_MODES:
        result = await decode(dut, map_mode, shared_wram_address)
        assert_target(result, "wram", 0x0123, map_mode, shared_wram_address)
        observations.append(result["wram_address"])

    assert len(set(observations)) == 1


@cocotb.test()
async def unsupported_map_mode_leaves_cartridge_space_unselected(dut):
    for address in (0x006000, 0x008000, 0x400000, 0xC00000, 0xFFFFFF):
        result = await decode(dut, 3, address)
        assert_target(result, None, None, 3, address)

    for address in (0x000000, 0x002100, 0x7E1234):
        result = await decode(dut, 3, address)
        expected_target, expected_address = reference_decode(MAP_LOROM, address)
        assert_target(result, expected_target, expected_address, 3, address)


@cocotb.test()
async def every_mode_matches_reference_across_all_banks(dut):
    offsets = (
        0x0000,
        0x1234,
        0x1FFF,
        0x2000,
        0x2345,
        0x5FFF,
        0x6000,
        0x6001,
        0x6ABC,
        0x7FFF,
        0x8000,
        0x8123,
        0xBEEF,
        0xFFFF,
    )

    for map_mode in ALL_MAP_MODES:
        for bank in range(0x100):
            for offset in offsets:
                await assert_matches_reference(
                    dut, map_mode, cpu_address(bank, offset)
                )
