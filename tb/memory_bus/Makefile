SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/catridge/cartridge_memory.sv \
                   $(PROJECT_ROOT)/rtl/memory/wram.sv \
                   $(PROJECT_ROOT)/rtl/catridge/memory_bus.sv

COCOTB_TOPLEVEL := memory_bus
COCOTB_TEST_MODULES := test_memory_bus

SIM_BUILD := $(PROJECT_ROOT)/build/memory_bus
COMPILE_ARGS += --sv --timing --timescale 1ns/1ps -Wall -Wno-fatal

include $(shell cocotb-config --makefiles)/Makefile.sim
