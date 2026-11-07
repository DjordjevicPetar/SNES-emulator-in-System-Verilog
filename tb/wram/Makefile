SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/memory/wram.sv

COCOTB_TOPLEVEL := wram
COCOTB_TEST_MODULES := test_wram

SIM_BUILD := $(PROJECT_ROOT)/build/wram

COMPILE_ARGS += --sv --timing --timescale 1ns/1ps

include $(shell cocotb-config --makefiles)/Makefile.sim