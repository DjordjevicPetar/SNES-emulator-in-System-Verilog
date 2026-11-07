module alu (
    // Inputs
    input logic [15:0] a_i,
    input logic [15:0] b_i,
    input alu_op_pkg::alu_op_t op_i,
    input logic is_16bit_i,
    input logic carry_i,

    // Flags output
    output logic negative_o,
    output logic zero_o,
    output logic carry_o,
    output logic overflow_o,

    // Result output
    output logic [15:0] result_o
);

logic [7:0] a_8bit;
logic [7:0] b_8bit;
logic [7:0] result_8bit;

always_comb begin
    a_8bit = a_i[7:0];
    b_8bit = b_i[7:0];
    result_o = '0;
    result_8bit = '0;
    carry_o = '0;
    overflow_o = '0;
    negative_o = '0;
    zero_o = '0;

    unique case (op_i)
        alu_op_pkg::ALU_OP_ADD: begin
            if (!is_16bit_i) begin
                {carry_o, result_8bit} = {1'b0, a_8bit} + {1'b0, b_8bit};
                overflow_o = (a_8bit[7] == b_8bit[7]) && (result_8bit[7] != a_8bit[7]);
            end else begin
                {carry_o, result_o} = {1'b0, a_i} + {1'b0, b_i};
                overflow_o = (a_i[15] == b_i[15]) && (result_o[15] != a_i[15]);
            end
        end
        alu_op_pkg::ALU_OP_SUB: begin
            if (!is_16bit_i) begin
                result_8bit = a_8bit - b_8bit;
                carry_o = a_8bit >= b_8bit;
                overflow_o = (a_8bit[7] != b_8bit[7]) && (result_8bit[7] != a_8bit[7]);
            end else begin
                result_o = a_i - b_i;
                carry_o = a_i >= b_i;
                overflow_o = (a_i[15] != b_i[15]) && (result_o[15] != a_i[15]);
            end
        end
        alu_op_pkg::ALU_OP_ADC: begin
            if (!is_16bit_i) begin
                {carry_o, result_8bit} = {1'b0, a_8bit} + {1'b0, b_8bit} + carry_i;
                overflow_o = (a_8bit[7] == b_8bit[7]) && (result_8bit[7] != a_8bit[7]);
            end else begin
                {carry_o, result_o} = {1'b0, a_i} + {1'b0, b_i} + carry_i;
                overflow_o = (a_i[15] == b_i[15]) && (result_o[15] != a_i[15]);
            end
        end
        alu_op_pkg::ALU_OP_SBC: begin
            if (!is_16bit_i) begin
                result_8bit = a_8bit - b_8bit - (1 - carry_i);
                carry_o = a_8bit >= b_8bit + (1 - carry_i);
                overflow_o = (a_8bit[7] != b_8bit[7]) && (result_8bit[7] != a_8bit[7]);
            end else begin
                result_o = a_i - b_i - (1 - carry_i);
                carry_o = a_i >= b_i + (1 - carry_i);
                overflow_o = (a_i[15] != b_i[15]) && (result_o[15] != a_i[15]);
            end
        end
        alu_op_pkg::ALU_OP_AND: begin
            if (!is_16bit_i) begin
                result_8bit = a_8bit & b_8bit;
            end else begin
                result_o = a_i & b_i;
            end
        end
        alu_op_pkg::ALU_OP_OR: begin
            if (!is_16bit_i) begin
                result_8bit = a_8bit | b_8bit;
            end else begin
                result_o = a_i | b_i;
            end
        end
        alu_op_pkg::ALU_OP_XOR: begin
            if (!is_16bit_i) begin
                result_8bit = a_8bit ^ b_8bit;
            end else begin
                result_o = a_i ^ b_i;
            end
        end
        alu_op_pkg::ALU_OP_ASL: begin
            if (!is_16bit_i) begin
                {carry_o, result_8bit} = {a_8bit, 1'b0};
            end else begin
                {carry_o, result_o} = {a_i, 1'b0};
            end
        end
        alu_op_pkg::ALU_OP_LSR: begin
            if (!is_16bit_i) begin
                {result_8bit, carry_o} = {1'b0, a_8bit};
            end else begin
                {result_o, carry_o} = {1'b0, a_i};
            end
        end
        alu_op_pkg::ALU_OP_ROL: begin
            if (!is_16bit_i) begin
                {carry_o, result_8bit} = {a_8bit, carry_i};
            end else begin
                {carry_o, result_o} = {a_i, carry_i};
            end
        end
        alu_op_pkg::ALU_OP_ROR: begin
            if (!is_16bit_i) begin
                {result_8bit, carry_o} = {carry_i, a_8bit};
            end else begin
                {result_o, carry_o} = {carry_i, a_i};
            end
        end
        default: begin
            result_o = '0;
            carry_o = '0;
            overflow_o = '0;
            negative_o = '0;
            zero_o = '0;
        end
    endcase

    if (is_16bit_i) begin
        negative_o = result_o[15];
        zero_o = (result_o == 16'b0000000000000000);
    end else begin
        negative_o = result_8bit[7];
        zero_o = (result_8bit == 8'b00000000);
    end

    if (!is_16bit_i) begin
        result_o[7:0] = result_8bit;
    end
end

endmodule
