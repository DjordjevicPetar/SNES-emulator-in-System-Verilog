.PHONY: test test-wram test-cartridge test-alu clean

test: test-wram test-cartridge test-alu

test-wram:
	$(MAKE) -C tb/wram

test-cartridge:
	$(MAKE) -C tb/cartridge_memory

test-alu:
	$(MAKE) -C tb/alu

clean:
	$(MAKE) -C tb/wram clean
	$(MAKE) -C tb/cartridge_memory clean
	$(MAKE) -C tb/alu clean
