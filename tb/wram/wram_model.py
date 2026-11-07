class WramModel:
    """Specification-level WRAM model with undefined power-up contents."""

    SIZE = 1 << 17
    LOW_RAM_SIZE = 1 << 13

    def __init__(self):
        self.memory = {}
        self.wm_address = 0

    def reset(self):
        self.wm_address = 0

    def a_write(self, address, data, *, full_address=True):
        effective_address = self.a_effective_address(address, full_address)
        self.memory[effective_address] = data

    def a_read(self, address, *, full_address=True):
        effective_address = self.a_effective_address(address, full_address)
        return self._read_initialized(effective_address)

    def wm_set_address(self, address):
        self.wm_address = address & (self.SIZE - 1)

    def wm_write(self, data):
        self.memory[self.wm_address] = data
        self.wm_address = (self.wm_address + 1) & (self.SIZE - 1)

    def wm_read(self):
        data = self._read_initialized(self.wm_address)
        self.wm_address = (self.wm_address + 1) & (self.SIZE - 1)
        return data

    @classmethod
    def a_effective_address(cls, address, full_address):
        if full_address:
            return address & (cls.SIZE - 1)
        return address & (cls.LOW_RAM_SIZE - 1)

    def _read_initialized(self, address):
        assert address in self.memory, (
            f"reference model read from unwritten WRAM address {address:#07x}"
        )
        return self.memory[address]
