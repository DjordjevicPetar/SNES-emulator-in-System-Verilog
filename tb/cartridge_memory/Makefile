SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/catridge/cartridge_memory.sv

COCOTB_TOPLEVEL := cartridge_memory
COCOTB_TEST_MODULES := test_cartridge_memory

SIM_BUILD := $(PROJECT_ROOT)/build/cartridge_memory

COMPILE_ARGS += --sv --timing --timescale 1ns/1ps -Wno-fatal

include $(shell cocotb-config --makefiles)/Makefile.sim
