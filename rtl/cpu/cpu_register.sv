module cpu_register (
    input logic clk_i,
    input logic reset_ni_i,

    input logic e_in_i,
    input logic e_write_i,
    output logic e_out_o,

    input logic [15:0] a_in_i,
    input logic a_write_8bit_i,
    input logic a_write_16bit_i,
    output logic [15:0] a_out_o,

    input logic [7:0] dbr_in_i,
    input logic dbr_write_i,
    output logic [7:0] dbr_out_o,

    input logic [15:0] d_in_i,
    input logic d_write_16bit_i,
    output logic [15:0] d_out_o,

    input logic [7:0] pbr_in_i,
    input logic pbr_write_i,
    output logic [7:0] pbr_out_o,

    input logic [15:0] pc_in_i,
    input logic pc_write_16bit_i,
    input logic pc_inc_i,
    output logic [15:0] pc_out_o,

    input logic [15:0] sp_in_i,
    input logic sp_write_16bit_i,
    input logic sp_inc_i,
    input logic sp_dec_i,
    output logic [15:0] sp_out_o,

    input logic [7:0] p_in_i,
    input logic p_write_i,
    input logic [7:0] p_mask_i,
    output logic [7:0] p_out_o,

    input logic [15:0] x_in_i,
    input logic x_write_8bit_i,
    input logic x_write_16bit_i,
    output logic [15:0] x_out_o,

    input logic [15:0] y_in_i,
    input logic y_write_8bit_i,
    input logic y_write_16bit_i,
    output logic [15:0] y_out_o
);

logic e_reg;
logic [15:0] a_reg;
logic [7:0] dbr_reg;
logic [15:0] d_reg;
logic [7:0] pbr_reg;
logic [15:0] pc_reg;
logic [7:0] p_reg;
logic [15:0] sp_reg;
logic [15:0] x_reg;
logic [15:0] y_reg;

// For comb logic calculations
logic e_d;
logic [7:0] p_d;

always_ff @(posedge clk_i or negedge reset_ni_i) begin : assertions
    if (reset_ni_i) begin
        assert (!(a_write_8bit_i && a_write_16bit_i))
            else $fatal(1, "ASSERT_A_WRITE_CONFLICT: simultaneous 8-bit and 16-bit A writes");
        assert (!(x_write_8bit_i && x_write_16bit_i))
            else $fatal(1, "ASSERT_X_WRITE_CONFLICT: simultaneous 8-bit and 16-bit X writes");
        assert (!(y_write_8bit_i && y_write_16bit_i))
            else $fatal(1, "ASSERT_Y_WRITE_CONFLICT: simultaneous 8-bit and 16-bit Y writes");
        assert (!(sp_inc_i && sp_dec_i))
            else $fatal(1, "ASSERT_SP_INC_DEC_CONFLICT: simultaneous SP increment and decrement");
    end
end

always_comb begin : d_calculation
    e_d = (e_reg & !e_write_i) | (e_in_i & e_write_i);
    if (p_write_i) begin
        p_d = (p_in_i & p_mask_i) | (p_reg & ~p_mask_i);
    end
    else begin
        p_d = p_reg;
    end

    if (e_d) begin
        p_d[5:4] = 2'b11;
    end
end


always_ff @(posedge clk_i or negedge reset_ni_i) begin
    if (!reset_ni_i) begin
        e_reg <= 1'b1;
        a_reg <= 16'h0000;
        dbr_reg <= 8'h00;
        d_reg <= 16'h0000;
        pbr_reg <= 8'h00;
        pc_reg <= 16'h0000;
        p_reg <= 8'h34;
        sp_reg <= 16'h01ff;
        x_reg <= 16'h0000;
        y_reg <= 16'h0000;
    end
    else begin
        e_reg <= e_d;
        if (a_write_8bit_i) begin
            a_reg[7:0] <= a_in_i[7:0];
        end
        else if (a_write_16bit_i) begin
            a_reg <= a_in_i;
        end
        if (dbr_write_i) begin
            dbr_reg <= dbr_in_i;
        end
        if (d_write_16bit_i) begin
            d_reg <= d_in_i;
        end
        if (pbr_write_i) begin
            pbr_reg <= pbr_in_i;
        end
        if (pc_write_16bit_i) begin
            pc_reg <= pc_in_i;
        end
        else if (pc_inc_i) begin
            pc_reg <= pc_reg + 1'b1;
        end
        if (sp_write_16bit_i) begin
            sp_reg <= sp_in_i;
        end
        else if (sp_inc_i) begin
            sp_reg <= sp_reg + 1'b1;
        end
        else if (sp_dec_i) begin
            sp_reg <= sp_reg - 1'b1;
        end
        p_reg <= p_d;
        if (x_write_8bit_i) begin
            x_reg <= {8'h00, x_in_i[7:0]};
        end
        else if (x_write_16bit_i) begin
            x_reg <= x_in_i;
        end
        if (y_write_8bit_i) begin
            y_reg <= {8'h00, y_in_i[7:0]};
        end
        else if (y_write_16bit_i) begin
            y_reg <= y_in_i;
        end
    end

    if (p_d[4]) begin
        x_reg[15:8] <= 8'h00;
        y_reg[15:8] <= 8'h00;
    end

    if (e_d) begin
        sp_reg[15:8] <= 8'h01;
    end
end

assign e_out_o = e_reg;
assign a_out_o = a_reg;
assign dbr_out_o = dbr_reg;
assign d_out_o = d_reg;
assign pbr_out_o = pbr_reg;
assign pc_out_o = pc_reg;
assign p_out_o = p_reg;
assign sp_out_o = sp_reg;
assign x_out_o = x_reg;
assign y_out_o = y_reg;

endmodule
