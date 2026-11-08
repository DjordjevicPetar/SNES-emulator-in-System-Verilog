SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/cpu/cpu_register.sv

COCOTB_TOPLEVEL := cpu_register
COCOTB_TEST_MODULES := test_cpu_register,test_cpu_register_storage

SIM_BUILD := $(PROJECT_ROOT)/build/cpu_register
COMPILE_ARGS += --sv --timing --timescale 1ns/1ps -Wall

include $(shell cocotb-config --makefiles)/Makefile.sim

# A failed SV assertion stops the simulator. Check invalid inputs in a separate
# process so the normal cocotb regression can still exercise every legal case.
.PHONY: check-assertion
check-assertion:
	verilator --binary --sv --timing --timescale 1ns/1ps --autoflush -Wall \
		--top-module cpu_register_assertion_tb \
		--Mdir $(SIM_BUILD)/assertion \
		$(VERILOG_SOURCES) $(CURDIR)/cpu_register_assertion_tb.sv
	python check_write_assertion.py $(SIM_BUILD)/assertion/Vcpu_register_assertion_tb
