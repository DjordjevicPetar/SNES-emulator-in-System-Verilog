SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/cpu/alu_op_pkg.sv \
                   $(PROJECT_ROOT)/rtl/cpu/alu.sv \
                   $(PROJECT_ROOT)/rtl/cpu/cpu_register.sv \
                   $(PROJECT_ROOT)/rtl/cpu/cpu_datapath.sv

COCOTB_TOPLEVEL := cpu_datapath
COCOTB_TEST_MODULES := test_cpu_datapath
SIM_BUILD := $(PROJECT_ROOT)/build/cpu_datapath
COMPILE_ARGS += --sv --timing --timescale 1ns/1ps --assert -Wall

include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: check-assertions
check-assertions:
	verilator --binary --sv --timing --timescale 1ns/1ps --assert --autoflush -Wall \
		--top-module cpu_datapath_assertion_tb --Mdir $(SIM_BUILD)/assertion \
		$(VERILOG_SOURCES) $(CURDIR)/cpu_datapath_assertion_tb.sv
	python check_command_assertions.py $(SIM_BUILD)/assertion/Vcpu_datapath_assertion_tb
