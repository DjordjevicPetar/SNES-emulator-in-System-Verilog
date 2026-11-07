SIM ?= verilator
TOPLEVEL_LANG := verilog

PROJECT_ROOT := $(abspath ../..)
# Packages must be compiled before modules that use their types.
VERILOG_SOURCES := $(PROJECT_ROOT)/rtl/cpu/alu_op_pkg.sv \
                   $(PROJECT_ROOT)/rtl/cpu/alu.sv

COCOTB_TOPLEVEL := alu
COCOTB_TEST_MODULES := test_alu

SIM_BUILD := $(PROJECT_ROOT)/build/alu
COMPILE_ARGS += --sv --timing --timescale 1ns/1ps -Wall -Wno-fatal

include $(shell cocotb-config --makefiles)/Makefile.sim
