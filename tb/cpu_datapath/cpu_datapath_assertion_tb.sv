module cpu_datapath_assertion_tb;
timeunit 1ns;
timeprecision 1ps;

logic clk = 1'b0;
logic reset_n = 1'b1;
logic [15:0] operand = 16'h0012;
alu_op_pkg::alu_op_t op = alu_op_pkg::ALU_OP_ADD;
logic execute = 1'b0;
logic load_a = 1'b0;
logic [7:0] p_data = 8'h00;
logic [7:0] p_mask = 8'hff;
logic p_write = 1'b0;
logic e_data = 1'b0;
logic e_write = 1'b0;
logic [15:0] a;
logic [7:0] p;
logic e;
logic native_mode;
logic decimal_case;
string test_case;
string mode;

cpu_datapath dut (
    .clk_i(clk),
    .reset_ni_i(reset_n),
    .operand_i(operand),
    .op_i(op),
    .alu_exec_i(execute),
    .a_load_i(load_a),
    .p_in_i(p_data),
    .p_mask_i(p_mask),
    .p_write_i(p_write),
    .e_in_i(e_data),
    .e_write_i(e_write),
    .a_out_o(a),
    .p_out_o(p),
    .e_out_o(e)
);

task automatic tick;
    #1 clk = 1'b1;
    #1 clk = 1'b0;
endtask

initial begin
    if (!$value$plusargs("case=%s", test_case)) $fatal(1, "Specify +case");
    if (!$value$plusargs("mode=%s", mode)) $fatal(1, "Specify +mode");
    if (mode != "native16" && mode != "emulation") $fatal(1, "Unknown mode");
    native_mode = mode == "native16";
    decimal_case = test_case == "decimal_adc" || test_case == "decimal_sbc";
    #1 reset_n = 1'b0;
    tick();
    if (a != 0 || p != 8'h34 || e != 1'b1) $fatal(1, "Reset setup failed");
    #1 reset_n = 1'b1;
    e_data = !native_mode;
    e_write = 1'b1;
    p_write = 1'b1;
    tick();
    e_write = 1'b0;
    p_write = 1'b0;
    load_a = 1'b1;
    tick();
    load_a = 1'b0;

    if (decimal_case) begin
        p_data = 8'h08;
        p_mask = 8'h08;
        p_write = 1'b1;
        tick();
        p_write = 1'b0;
    end
    if (a != 16'h0012 || e != !native_mode ||
            p != ((native_mode ? 8'h00 : 8'h30) | (decimal_case ? 8'h08 : 8'h00)))
        $fatal(1, "Valid command setup failed before the invalid request");

    $display("BEGIN_INVALID_COMMAND");
    case (test_case)
        "load_execute": begin load_a = 1'b1; execute = 1'b1; end
        "load_p": begin load_a = 1'b1; p_write = 1'b1; end
        "execute_p": begin execute = 1'b1; p_write = 1'b1; end
        "load_e": begin load_a = 1'b1; e_write = 1'b1; end
        "execute_e": begin execute = 1'b1; e_write = 1'b1; end
        "invalid_op": begin
            execute = 1'b1;
            op = alu_op_pkg::alu_op_t'(8'hff);
        end
        "decimal_adc": begin execute = 1'b1; op = alu_op_pkg::ALU_OP_ADC; end
        "decimal_sbc": begin execute = 1'b1; op = alu_op_pkg::ALU_OP_SBC; end
        default: $fatal(1, "Unknown case: %s", test_case);
    endcase
    tick();
    $display("COMMAND_WAS_NOT_REJECTED");
    $finish;
end
endmodule
