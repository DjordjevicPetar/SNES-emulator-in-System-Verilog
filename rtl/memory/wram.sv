module wram (
    input logic        clk_i,
    input logic        refresh_i, // TODO: Unused on Cyclone V, but important for cycle accuracy
    input logic        reset_ni,

    // Address bus A
    input logic        ram_sel_ni,
    input logic        enable_i,
    input logic        a_bus_rd_ni,
    input logic        a_bus_wr_ni,
    input logic [16:0] a_bus_i,

    // Address bus B
    input logic        b_bus_rd_ni,
    input logic        b_bus_wr_ni,
    input logic [7:0]  b_bus_i,
    
    // Data bus
    input logic [7:0] data_bus_i,
    output logic [7:0] data_bus_o,
    output logic data_bus_oe_o
);

// Functional model: one operation per asserted clock cycle.
// TODO(timing): Model SNES access delays and refresh stalls in the bus controller.

localparam int WRAM_SIZE = 131072; // 128KB
logic [7:0] wram_data [WRAM_SIZE-1:0];
logic map_hit;
assign map_hit = b_bus_i[7:2] == 6'b100000; // $2180h - $2183h

logic           a_read_req;
logic           a_write_req;
logic           b_read_req;
logic           b_write_req;
logic [16:0]    a_effective_addr;

assign a_read_req = !ram_sel_ni && !a_bus_rd_ni;
assign a_write_req = !ram_sel_ni && !a_bus_wr_ni;
assign b_read_req = map_hit && !b_bus_rd_ni && (b_bus_i[1:0] == 2'b00);
assign b_write_req = map_hit && !b_bus_wr_ni;
assign a_effective_addr = (enable_i) ? a_bus_i : {4'b0000, a_bus_i[12:0]};

logic [16:0] wm_addr_q;

always_ff @(posedge clk_i or negedge reset_ni) begin
    data_bus_oe_o <= 1'b0;

    if (!reset_ni) begin
        wm_addr_q <= '0;
        data_bus_o <= '0;
    end else begin
        // TODO(accuracy): Verify behavior of simultaneous A-bus and B-bus accesses.
        if (a_read_req) begin
            data_bus_o <= wram_data[a_effective_addr];
            data_bus_oe_o <= 1'b1;
        end else if (a_write_req) begin
            wram_data[a_effective_addr] <= data_bus_i;
        end else if (b_read_req) begin
            data_bus_o <= wram_data[wm_addr_q];
            wm_addr_q <= wm_addr_q + 1;
            data_bus_oe_o <= 1'b1;
        end else if (b_write_req) begin
            case (b_bus_i[1:0])
                2'b00: begin
                    wram_data[wm_addr_q] <= data_bus_i;
                    wm_addr_q <= wm_addr_q + 1;
                end
                2'b01: wm_addr_q[7:0] <= data_bus_i;
                2'b10: wm_addr_q[15:8] <= data_bus_i;
                2'b11: wm_addr_q[16] <= data_bus_i[0];
            endcase
        end
    end
end

endmodule