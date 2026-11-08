from dataclasses import dataclass
from typing import Optional

from cocotb.triggers import Timer


@dataclass(frozen=True)
class BusCycle:
    ready: bool
    data: Optional[int]


@dataclass(frozen=True)
class BusTransfer:
    data: int
    latency_cycles: int


class MemoryBusDriver:
    """CPU-side requests with a manually stepped clock and bounded waits.

    cycle() samples WRAM strobes BEFORE the accepting edge and CPU outputs
    AFTER it. Only the passive strobe counter knows about the WRAM instance;
    transactions and memory checks use the public memory_bus interface.
    """

    def __init__(self, dut, map_mode=0, clock_period_ns=10):
        self.dut = dut
        self.map_mode = map_mode
        self.half_period_ns = clock_period_ns / 2
        self.wram_reads = 0
        self.wram_writes = 0
        self.ready_cycles = 0
        self._started = False

    def drive_idle(self):
        self.dut.req_i.value = 0
        self.dut.wr_i.value = 0
        self.dut.addr_i.value = 0
        self.dut.wr_data_i.value = 0

    async def start(self):
        if self._started:
            raise RuntimeError("memory bus driver has already started")
        self.dut.clk_i.value = 0
        self.dut.reset_ni.value = 0
        self.dut.map_mode_i.value = self.map_mode
        self.drive_idle()
        self._started = True
        await self.reset()

    async def cycle(self):
        if not self._started:
            raise RuntimeError("call await bus.start() first")
        self.dut.clk_i.value = 0
        await Timer(self.half_period_ns, unit="ns")

        if int(self.dut.reset_ni.value):
            wram = self.dut.wram_i
            selected = not int(wram.wram_sel_ni.value)
            reading = not int(wram.a_bus_rd_ni.value)
            writing = not int(wram.a_bus_wr_ni.value)
            assert not (reading and writing), "simultaneous WRAM read/write strobes"
            if not int(self.dut.req_i.value):
                assert not (reading or writing), "WRAM strobe without a CPU request"
            self.wram_reads += int(selected and reading)
            self.wram_writes += int(selected and writing)

        self.dut.clk_i.value = 1
        await Timer(self.half_period_ns, unit="ns")
        ready = bool(int(self.dut.ready_o.value))
        self.ready_cycles += int(ready)
        data = int(self.dut.rd_data_o.value) if ready else None
        return BusCycle(ready, data)

    async def reset(self, cycles=2):
        self.drive_idle()
        self.dut.reset_ni.value = 0
        for _ in range(cycles):
            observation = await self.cycle()
            assert not observation.ready, "bus acknowledged a request during reset"
        self.dut.reset_ni.value = 1
        await self.idle(1)

    async def idle(self, cycles=1):
        self.drive_idle()
        for _ in range(cycles):
            observation = await self.cycle()
            assert not observation.ready, "idle bus generated a ready pulse"

    def drive_request(self, address, *, write=False, data=0):
        self.dut.addr_i.value = address
        self.dut.wr_i.value = int(write)
        self.dut.wr_data_i.value = data
        self.dut.req_i.value = 1

    async def transfer(self, address, *, write=False, data=0, hold_cycles=0):
        before_ready = self.ready_cycles
        self.drive_request(address, write=write, data=data)
        observation = None
        latency = 0
        for latency in range(1, 9):
            observation = await self.cycle()
            if observation.ready:
                break
        else:
            raise AssertionError(f"request to {address:#08x} did not complete in 8 cycles")

        result = BusTransfer(observation.data, latency)
        for _ in range(hold_cycles):
            held = await self.cycle()
            assert not held.ready, "holding req_i high caused a repeated acknowledgement"

        # A full clock with req_i low rearms the documented request protocol.
        self.dut.req_i.value = 0
        released = await self.cycle()
        assert not released.ready, "ready_o lasted longer than one clock"
        assert self.ready_cycles - before_ready == 1, "request completed more than once"
        return result

    async def write(self, address, data, *, hold_cycles=0):
        return await self.transfer(address, write=True, data=data, hold_cycles=hold_cycles)

    async def read(self, address, *, hold_cycles=0):
        result = await self.transfer(address, hold_cycles=hold_cycles)
        return result.data
