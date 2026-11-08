module cpu_datapath (
    input logic clk_i,
    input logic reset_ni_i,

    input logic [15:0] operand_i,
    input alu_op_pkg::alu_op_t op_i,

    input logic alu_exec_i,
    input logic a_load_i,

    input logic [7:0] p_in_i,
    input logic [7:0] p_mask_i,
    input logic p_write_i,
    input logic e_in_i,
    input logic e_write_i,

    output logic [15:0] a_out_o,
    output logic [7:0] p_out_o,
    output logic e_out_o
);

// _q wires read stored state. _d wires carry a candidate for the next write.
logic [15:0] a_q, a_d;
logic [7:0] p_q, p_d;
logic e_q;
logic a_write;
logic p_write;
logic [7:0] p_mask;

logic [15:0] alu_result;
logic alu_negative, alu_zero, alu_carry, alu_overflow;
logic [7:0] alu_flag_mask;
logic alu_op_valid;

logic [7:0] unused_dbr, unused_pbr;
logic [15:0] unused_d, unused_pc, unused_sp, unused_x, unused_y;

assign a_out_o = a_q;
assign p_out_o = p_q;
assign e_out_o = e_q;
assign a_write = a_load_i || alu_exec_i;

alu alu_inst (
    .a_i(a_q),
    .b_i(operand_i),
    .op_i(op_i),
    .is_16bit_i(!p_q[5]),
    .carry_i(p_q[0]),
    .negative_o(alu_negative),
    .zero_o(alu_zero),
    .carry_o(alu_carry),
    .overflow_o(alu_overflow),
    .result_o(alu_result)
);

always_comb begin : select_alu_flags
    alu_flag_mask = 8'h00;
    alu_op_valid = 1'b1;
    unique case (op_i)
        alu_op_pkg::ALU_OP_ADD, alu_op_pkg::ALU_OP_SUB,
        alu_op_pkg::ALU_OP_ADC, alu_op_pkg::ALU_OP_SBC:
            alu_flag_mask = 8'hc3;
        alu_op_pkg::ALU_OP_AND, alu_op_pkg::ALU_OP_OR, alu_op_pkg::ALU_OP_XOR:
            alu_flag_mask = 8'h82;
        alu_op_pkg::ALU_OP_ASL, alu_op_pkg::ALU_OP_LSR,
        alu_op_pkg::ALU_OP_ROL, alu_op_pkg::ALU_OP_ROR:
            alu_flag_mask = 8'h83;
        default: alu_op_valid = 1'b0;
    endcase
end

always_comb begin : select_register_inputs
    a_d = a_q;
    p_d = p_in_i;
    p_mask = p_mask_i;
    p_write = p_write_i;

    if (alu_exec_i) begin
        a_d = alu_result;
        p_d = {alu_negative, alu_overflow, 4'b0000, alu_zero, alu_carry};
        p_mask = alu_flag_mask;
        p_write = 1'b1;
    end else if (a_load_i) begin
        a_d = operand_i;
        p_d = 8'h00;
        if (p_q[5]) begin
            p_d[7] = operand_i[7];
            p_d[1] = operand_i[7:0] == 8'h00;
        end else begin
            p_d[7] = operand_i[15];
            p_d[1] = operand_i == 16'h0000;
        end
        p_mask = 8'h82;
        p_write = 1'b1;
    end
end

always_ff @(posedge clk_i or negedge reset_ni_i) begin : check_commands
    if (reset_ni_i) begin
        assert (!(a_load_i && alu_exec_i))
            else $fatal(1, "ASSERT_DP_A_CONFLICT: load and ALU execute requested together");
        assert (!(a_write && (p_write_i || e_write_i)))
            else $fatal(1, "ASSERT_DP_CONTROL_CONFLICT: data and direct P/E writes conflict");
        assert (!alu_exec_i || alu_op_valid)
            else $fatal(1, "ASSERT_DP_INVALID_OP: unsupported ALU operation");
        assert (!(alu_exec_i && p_q[3] &&
                            (op_i == alu_op_pkg::ALU_OP_ADC || op_i == alu_op_pkg::ALU_OP_SBC)))
            else $fatal(1, "ASSERT_DP_DECIMAL_UNSUPPORTED: ADC/SBC currently require D=0");
    end
end

cpu_register cpu_register_inst (
    .clk_i(clk_i),
    .reset_ni_i(reset_ni_i),
    .e_in_i(e_in_i),
    .e_write_i(e_write_i),
    .e_out_o(e_q),
    .a_in_i(a_d),
    .a_write_8bit_i(a_write && p_q[5]),
    .a_write_16bit_i(a_write && !p_q[5]),
    .a_out_o(a_q),
    .dbr_in_i(8'h00),
    .dbr_write_i(1'b0),
    .dbr_out_o(unused_dbr),
    .d_in_i(16'h0000),
    .d_write_16bit_i(1'b0),
    .d_out_o(unused_d),
    .pbr_in_i(8'h00),
    .pbr_write_i(1'b0),
    .pbr_out_o(unused_pbr),
    .pc_in_i(16'h0000),
    .pc_write_16bit_i(1'b0),
    .pc_inc_i(1'b0),
    .pc_out_o(unused_pc),
    .sp_in_i(16'h0000),
    .sp_write_16bit_i(1'b0),
    .sp_inc_i(1'b0),
    .sp_dec_i(1'b0),
    .sp_out_o(unused_sp),
    .p_in_i(p_d),
    .p_write_i(p_write),
    .p_mask_i(p_mask),
    .p_out_o(p_q),
    .x_in_i(16'h0000),
    .x_write_8bit_i(1'b0),
    .x_write_16bit_i(1'b0),
    .x_out_o(unused_x),
    .y_in_i(16'h0000),
    .y_write_8bit_i(1'b0),
    .y_write_16bit_i(1'b0),
    .y_out_o(unused_y)
);

endmodule
