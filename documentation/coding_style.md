# SystemVerilog coding style

This project follows a small, beginner-friendly subset of the
[lowRISC Verilog coding style](https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md).
Consistency inside this project is more important than copying every rule from
the full guide.

## Files and directories

- Synthesizable design files go in `rtl/`.
- Testbenches go in `tb/`.
- Use the `.sv` extension.
- Put one main module in each file.
- The filename must match the module name: module `address_decoder` belongs in
  `address_decoder.sv`.

## Names

- Modules, instances, ports, signals, variables, functions, and tasks use
  `lower_snake_case`.
- Tunable module parameters use `UpperCamelCase`.
- Constants and `localparam` values use `ALL_CAPS`.
- Type names end in `_t`; enumeration type names end in `_e`.
- Testbench modules use the `_tb` suffix and instantiate the design under test
  as `dut`.

## Port and signal suffixes

- Module input: `_i`
- Module output: `_o`
- Bidirectional port: `_io`
- Active-low signal: `_n`
- Active-low input/output: `_ni` / `_no`
- Registered value: `_q`
- Corresponding next value: `_d`

Examples:

```systemverilog
input  logic        clk_i;
input  logic        rst_ni;
input  logic [23:0] cpu_addr_i;
output logic        wram_sel_no;
output logic [7:0]  read_data_o;
```

## Formatting

- Indent with two spaces; do not use tabs.
- Put spaces around operators.
- Write packed vectors as `logic [23:0] address`.
- Keep lines at approximately 100 characters or fewer.
- End every non-empty file with a newline.
