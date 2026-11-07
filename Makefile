.PHONY: test test-wram test-cartridge clean

test: test-wram test-cartridge

test-wram:
	$(MAKE) -C tb/wram

test-cartridge:
	$(MAKE) -C tb/cartridge_memory

clean:
	$(MAKE) -C tb/wram clean
	$(MAKE) -C tb/cartridge_memory clean
