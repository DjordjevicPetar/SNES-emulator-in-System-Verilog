.PHONY: test test-wram test-cartridge test-memory-bus test-cpu-register \
        test-cpu-datapath test-alu clean

test: test-wram test-cartridge test-memory-bus test-cpu-register \
      test-cpu-datapath test-alu

test-wram:
	$(MAKE) -C tb/wram

test-cartridge:
	$(MAKE) -C tb/cartridge_memory

test-memory-bus:
	$(MAKE) -C tb/memory_bus

test-cpu-register:
	$(MAKE) -C tb/cpu_register
	$(MAKE) -C tb/cpu_register check-assertion

test-cpu-datapath:
	$(MAKE) -C tb/cpu_datapath
	$(MAKE) -C tb/cpu_datapath check-assertions

test-alu:
	$(MAKE) -C tb/alu

clean:
	$(MAKE) -C tb/wram clean
	$(MAKE) -C tb/cartridge_memory clean
	$(MAKE) -C tb/memory_bus clean
	$(MAKE) -C tb/cpu_register clean
	$(MAKE) -C tb/cpu_datapath clean
	$(MAKE) -C tb/alu clean
