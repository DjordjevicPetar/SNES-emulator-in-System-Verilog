from dataclasses import dataclass
from typing import Optional

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


WMDATA = 0x80
WMADDL = 0x81
WMADDM = 0x82
WMADDH = 0x83


@dataclass(frozen=True)
class BusObservation:
    output_enabled: bool
    data: Optional[int]


class WramDriver:
    """Transaction-level interface for the external WRAM ports."""

    def __init__(self, dut, clock_period_ns=10):
        self.dut = dut
        self.clock_period_ns = clock_period_ns
        self._clock_started = False

    def drive_idle(self):
        self.dut.refresh_i.value = 0

        self.dut.ram_sel_ni.value = 1
        self.dut.enable_i.value = 0
        self.dut.a_bus_rd_ni.value = 1
        self.dut.a_bus_wr_ni.value = 1
        self.dut.a_bus_i.value = 0

        self.dut.b_bus_rd_ni.value = 1
        self.dut.b_bus_wr_ni.value = 1
        self.dut.b_bus_i.value = 0

        self.dut.data_bus_i.value = 0

    async def start(self):
        if self._clock_started:
            raise RuntimeError("WRAM clock has already been started")

        self.drive_idle()
        self.dut.reset_ni.value = 0
        cocotb.start_soon(
            Clock(self.dut.clk_i, self.clock_period_ns, unit="ns").start()
        )
        self._clock_started = True

        await ClockCycles(self.dut.clk_i, 2)
        await FallingEdge(self.dut.clk_i)
        self.dut.reset_ni.value = 1

    async def reset(self, cycles=2):
        self._require_started()
        if cycles < 1:
            raise ValueError("reset must last at least one clock cycle")

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        self.dut.reset_ni.value = 0

        await ClockCycles(self.dut.clk_i, cycles)
        await FallingEdge(self.dut.clk_i)
        self.dut.reset_ni.value = 1

    async def a_write(self, address, data, *, full_address=True, selected=True):
        self._require_started()
        self._check_width("A-bus address", address, 17)
        self._check_width("write data", data, 8)

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        self.dut.enable_i.value = int(full_address)
        self.dut.ram_sel_ni.value = 0 if selected else 1
        self.dut.a_bus_wr_ni.value = 0
        self.dut.a_bus_i.value = address
        self.dut.data_bus_i.value = data

        return await self._observe_and_release()

    async def a_read_cycle(self, address, *, full_address=True, selected=True):
        self._require_started()
        self._check_width("A-bus address", address, 17)

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        self.dut.enable_i.value = int(full_address)
        self.dut.ram_sel_ni.value = 0 if selected else 1
        self.dut.a_bus_rd_ni.value = 0
        self.dut.a_bus_i.value = address

        return await self._observe_and_release()

    async def a_read(self, address, *, full_address=True):
        observation = await self.a_read_cycle(
            address,
            full_address=full_address,
            selected=True,
        )
        assert observation.output_enabled, "selected A-bus read did not drive the data bus"
        return observation.data

    async def b_write_register(self, register, data):
        self._require_started()
        self._check_width("B-bus register", register, 8)
        self._check_width("write data", data, 8)

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        self.dut.b_bus_wr_ni.value = 0
        self.dut.b_bus_i.value = register
        self.dut.data_bus_i.value = data

        return await self._observe_and_release()

    async def b_read_register(self, register):
        self._require_started()
        self._check_width("B-bus register", register, 8)

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        self.dut.b_bus_rd_ni.value = 0
        self.dut.b_bus_i.value = register

        return await self._observe_and_release()

    async def wm_set_address(self, address):
        self._check_width("WM address", address, 17)
        await self.b_write_register(WMADDL, address & 0xFF)
        await self.b_write_register(WMADDM, (address >> 8) & 0xFF)
        await self.b_write_register(WMADDH, (address >> 16) & 0x01)

    async def wm_write(self, data):
        return await self.b_write_register(WMDATA, data)

    async def wm_read(self):
        observation = await self.b_read_register(WMDATA)
        assert observation.output_enabled, "WMDATA read did not drive the data bus"
        return observation.data

    async def _observe_and_release(self):
        await RisingEdge(self.dut.clk_i)
        await ReadOnly()

        output_enabled = bool(int(self.dut.data_bus_oe_o.value))
        data = int(self.dut.data_bus_o.value) if output_enabled else None
        observation = BusObservation(output_enabled, data)

        await FallingEdge(self.dut.clk_i)
        self.drive_idle()
        return observation

    def _require_started(self):
        if not self._clock_started:
            raise RuntimeError("call await driver.start() before issuing transactions")

    @staticmethod
    def _check_width(name, value, width):
        if not 0 <= value < (1 << width):
            raise ValueError(f"{name} must fit in {width} bits, got {value:#x}")
