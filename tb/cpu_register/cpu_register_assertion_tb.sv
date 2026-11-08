module cpu_register_assertion_tb;
  timeunit 1ns;
  timeprecision 1ps;

  logic clk = 1'b0;
  logic reset_n = 1'b1;
  logic a_write8 = 1'b0;
  logic a_write16 = 1'b0;
  logic x_write8 = 1'b0;
  logic x_write16 = 1'b0;
  logic y_write8 = 1'b0;
  logic y_write16 = 1'b0;
  logic e_write = 1'b0;
  logic p_write = 1'b0;
  logic storage_write = 1'b0;
  logic sp_write = 1'b0;
  logic sp_inc = 1'b0;
  logic sp_dec = 1'b0;
  logic [15:0] a;
  logic [15:0] pc;
  logic [7:0] p;
  logic [15:0] x;
  logic [15:0] y;
  logic e;
  logic [15:0] d;
  logic [7:0] dbr;
  logic [7:0] pbr;
  logic [15:0] sp;
  logic native_mode;
  string conflict;
  string mode;
  int stack_write;

  cpu_register dut (
    .clk_i(clk),
    .reset_ni_i(reset_n),
    .e_in_i(1'b0),
    .e_write_i(e_write),
    .e_out_o(e),
    .a_in_i(16'habcd),
    .a_write_8bit_i(a_write8),
    .a_write_16bit_i(a_write16),
    .a_out_o(a),
    .d_in_i(16'hbeef),
    .d_write_16bit_i(storage_write),
    .d_out_o(d),
    .dbr_in_i(8'ha5),
    .dbr_write_i(storage_write),
    .dbr_out_o(dbr),
    .pbr_in_i(8'h5a),
    .pbr_write_i(storage_write),
    .pbr_out_o(pbr),
    .sp_in_i(16'habcd),
    .sp_write_16bit_i(sp_write),
    .sp_inc_i(sp_inc),
    .sp_dec_i(sp_dec),
    .sp_out_o(sp),
    .pc_in_i(16'h0000),
    .pc_write_16bit_i(1'b0),
    .pc_inc_i(1'b0),
    .pc_out_o(pc),
    .p_in_i(8'h00),
    .p_write_i(p_write),
    .p_mask_i(8'hff),
    .p_out_o(p),
    .x_in_i(16'h1357),
    .x_write_8bit_i(x_write8),
    .x_write_16bit_i(x_write16),
    .x_out_o(x),
    .y_in_i(16'h2468),
    .y_write_8bit_i(y_write8),
    .y_write_16bit_i(y_write16),
    .y_out_o(y)
  );

  initial begin
    if (!$value$plusargs("conflict=%s", conflict))
      $fatal(1, "Specify +conflict=A, X, Y or SP");
    if (!$value$plusargs("stack_write=%d", stack_write)) stack_write = 0;
    if (!$value$plusargs("mode=%s", mode)) mode = "native";
    if (mode != "native" && mode != "emulation")
      $fatal(1, "Unknown mode: %s", mode);
    native_mode = mode == "native";
    #1 reset_n = 1'b0;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
    if (a != 0 || pc != 0 || p != 8'h34 || x != 0 || y != 0 || e != 1'b1 ||
        d != 0 || dbr != 0 || pbr != 0 || sp != 16'h01ff)
      $fatal(1, "Assertion checker reset failed before invalid request");
    reset_n = 1'b1;
    e_write = native_mode;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
    e_write = 1'b0;
    p_write = native_mode;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
    p_write = 1'b0;
    a_write16 = 1'b1;
    x_write16 = 1'b1;
    y_write16 = 1'b1;
    storage_write = 1'b1;
    sp_write = 1'b1;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
    a_write16 = 1'b0;
    x_write16 = 1'b0;
    y_write16 = 1'b0;
    storage_write = 1'b0;
    sp_write = 1'b0;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
    if (a != 16'habcd || pc != 16'h0000 ||
        p != (native_mode ? 8'h00 : 8'h34) || e != !native_mode ||
        x != (native_mode ? 16'h1357 : 16'h0057) ||
        y != (native_mode ? 16'h2468 : 16'h0068) ||
        d != 16'hbeef || dbr != 8'ha5 || pbr != 8'h5a ||
        sp != (native_mode ? 16'habcd : 16'h01cd))
      $fatal(1, "Assertion checker setup failed before invalid request");

    $display("BEGIN_INVALID_%s_WRITE", conflict);
    case (conflict)
      "A": begin
        a_write8 = 1'b1;
        a_write16 = 1'b1;
      end
      "X": begin
        x_write8 = 1'b1;
        x_write16 = 1'b1;
      end
      "Y": begin
        y_write8 = 1'b1;
        y_write16 = 1'b1;
      end
      "SP": begin
        sp_inc = 1'b1;
        sp_dec = 1'b1;
        sp_write = stack_write != 0;
      end
      default: $fatal(1, "Unknown conflict register: %s", conflict);
    endcase
    #1 clk = 1'b1;
    #1;
    $display("INVALID_%s_WRITE_WAS_NOT_REJECTED", conflict);
    $finish;
  end
endmodule
