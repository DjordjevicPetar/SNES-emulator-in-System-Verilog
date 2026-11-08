from cocotb.triggers import Timer

from cpu_register_model import RegisterState, RESET_STATE


class CpuRegisterDriver:
    """Drive one register update per rising edge and sample after it settles."""

    def __init__(self, dut):
        self.dut = dut

    def drive(self, *, a=0, a8=False, a16=False, pc=0, pc_write=False,
              pc_inc=False, p=0, p_write=False, p_mask=0xFF,
              x=0, x8=False, x16=False, y=0, y8=False, y16=False,
              e=0, e_write=False, d=0, d_write=False, dbr=0, dbr_write=False,
              pbr=0, pbr_write=False, sp=0, sp_write=False, sp_inc=False, sp_dec=False):
        self.dut.e_in_i.value = int(e)
        self.dut.e_write_i.value = int(e_write)
        self.dut.a_in_i.value = a
        self.dut.a_write_8bit_i.value = int(a8)
        self.dut.a_write_16bit_i.value = int(a16)
        self.dut.pc_in_i.value = pc
        self.dut.pc_write_16bit_i.value = int(pc_write)
        self.dut.pc_inc_i.value = int(pc_inc)
        self.dut.p_in_i.value = p
        self.dut.p_write_i.value = int(p_write)
        self.dut.p_mask_i.value = p_mask
        self.dut.x_in_i.value = x
        self.dut.x_write_8bit_i.value = int(x8)
        self.dut.x_write_16bit_i.value = int(x16)
        self.dut.y_in_i.value = y
        self.dut.y_write_8bit_i.value = int(y8)
        self.dut.y_write_16bit_i.value = int(y16)
        self.dut.d_in_i.value = d
        self.dut.d_write_16bit_i.value = int(d_write)
        self.dut.dbr_in_i.value = dbr
        self.dut.dbr_write_i.value = int(dbr_write)
        self.dut.pbr_in_i.value = pbr
        self.dut.pbr_write_i.value = int(pbr_write)
        self.dut.sp_in_i.value = sp
        self.dut.sp_write_16bit_i.value = int(sp_write)
        self.dut.sp_inc_i.value = int(sp_inc)
        self.dut.sp_dec_i.value = int(sp_dec)

    def snapshot(self):
        return RegisterState(
            int(self.dut.a_out_o.value),
            int(self.dut.pc_out_o.value),
            int(self.dut.p_out_o.value),
            int(self.dut.x_out_o.value),
            int(self.dut.y_out_o.value),
            int(self.dut.e_out_o.value),
            int(self.dut.d_out_o.value),
            int(self.dut.dbr_out_o.value),
            int(self.dut.pbr_out_o.value),
            int(self.dut.sp_out_o.value),
        )

    async def start(self):
        self.dut.clk_i.value = 0
        self.dut.reset_ni_i.value = 1
        self.drive()
        await Timer(1, unit="ns")
        await self.reset()

    async def reset(self):
        # Deliberately no clock edge: this must work through reset_ni alone.
        self.dut.reset_ni_i.value = 0
        await Timer(1, unit="ns")
        observed = self.snapshot()
        assert observed == RESET_STATE, (
            f"asynchronous reset: expected {RESET_STATE}, got {observed}"
        )
        self.dut.reset_ni_i.value = 1
        await Timer(1, unit="ns")

    async def tick(self):
        self.dut.clk_i.value = 0
        await Timer(5, unit="ns")
        self.dut.clk_i.value = 1
        await Timer(5, unit="ns")
        return self.snapshot()

    async def cycle(self, **inputs):
        self.drive(**inputs)
        return await self.tick()

    async def enter_native(self):
        # Use separate edges so ordinary register tests do not depend on the
        # specific same-edge E/P transition cases tested elsewhere.
        await self.cycle(e=0, e_write=True)
        return await self.cycle(p=0, p_write=True)
