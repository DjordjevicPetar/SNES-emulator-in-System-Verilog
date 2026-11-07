// Prva verzija: podrzan je samo WRAM preko A-busa.
// ROM, SRAM, I/O (B-bus) i open bus dolaze kasnije.
//
// Protokol (CPU strana):
//   P1  CPU drzi addr_i, wr_i i wr_data_i stabilnim dok je req_i = 1.
//   P2  Zahtev je prihvacen na ivici na kojoj je state == IDLE i req_i = 1.
//   P3  ready_o = 1 tacno jedan takt i oznacava da je pristup zavrsen.
//   P4  Novi zahtev se prihvata tek kada req_i padne na 0.
//       Tako se jedan zahtev izvrsava samo jednom.
//   P5  rd_data_o vazi samo dok je ready_o = 1.
//   P6  Bez req_i strobovi ka WRAM-u su neaktivni, pa nema upisa.

module memory_bus (
    input logic        clk_i,
    input logic        reset_ni,  //aktivan na 0
    input logic        req_i,     //postoji zahtev
    input logic        wr_i,      //1 - wr, 0 - rd
    input logic [23:0] addr_i,    //BB:AAAA
    input logic [7:0]  wr_data_i,
    output logic [7:0] rd_data_o, //vazi dok je ready_o = 1
    output logic       ready_o,   //1 takt - pristup zavrsen

    input logic [1:0]  map_mode_i
);

    logic        wram_sel;
    logic [16:0] wram_addr;
    logic        io_sel;     // jos se ne koristi
    logic [15:0] io_addr;    // jos se ne koristi
    logic        sram_sel;   // jos se ne koristi
    logic [18:0] sram_addr;  // jos se ne koristi
    logic        rom_sel;    // jos se ne koristi
    logic [22:0] rom_addr;   // jos se ne koristi

    cartridge_memory cartridge_memory_i (
        .map_mode_i(map_mode_i),
        .addr_i(addr_i),

        .wram_sel_o(wram_sel),
        .wram_addr_o(wram_addr),

        .io_sel_o(io_sel),
        .io_addr_o(io_addr),

        .sram_sel_o(sram_sel),
        .sram_addr_o(sram_addr),

        .rom_sel_o(rom_sel),
        .rom_addr_o(rom_addr)
    );


    /////////////////////////////////////// FSM /////////////////////////////////
    //Ideja: FSM odgovara na KADA, ostalo na GDE
    typedef enum logic [1:0] {IDLE, DONE, WAIT_RELEASE} state_t;
    state_t state_reg, state_next;

    //IDLE -> DONE (ready_o = 1) -> WAIT_RELEASE (ceka da req_i padne) -> IDLE
    //jedini takt u kome se zahtev prihvata i salje memoriji.
    logic accept;
    assign accept = (state_reg == IDLE) && req_i;

    always_ff @(posedge clk_i or negedge reset_ni) begin
        if (!reset_ni) state_reg <= IDLE;
        else           state_reg <= state_next;
    end

    always_comb begin
        state_next = state_reg;
        unique case (state_reg)
            IDLE:         if (req_i)  state_next = DONE;
            DONE:         state_next = req_i ? WAIT_RELEASE : IDLE;
            WAIT_RELEASE: if (!req_i) state_next = IDLE;
            default:      state_next = IDLE;
        endcase
    end

// WRAM (A-bus). Strobovi su aktivni na 0 i traju samo u "accept" taktu.
    // ------------------------------------------------------------------
    logic       wram_sel_n;
    logic       wram_rd_n;
    logic       wram_wr_n;
    logic [7:0] wram_rd_data;
    logic       wram_rd_data_oe;

    assign wram_sel_n = !(accept && wram_sel);  //n = suprotno, aktivan na 0
    assign wram_rd_n  = !(accept && wram_sel && !wr_i);
    assign wram_wr_n  = !(accept && wram_sel &&  wr_i);

    wram wram_i (
    .clk_i         (clk_i),
    .refresh_i     (1'b0),
    .reset_ni      (reset_ni),

    // A-bus: mirror vec racuna mapper, zato enable_i = 1 (puna adresa)
    .wram_sel_ni    (wram_sel_n),
    .enable_i      (1'b1),
    .a_bus_rd_ni   (wram_rd_n),
    .a_bus_wr_ni   (wram_wr_n),
    .a_bus_i       (wram_addr),

    // B-bus ($2180-$2183) jos nije povezan
    .b_bus_rd_ni   (1'b1),
    .b_bus_wr_ni   (1'b1),
    .b_bus_i       (8'h00),

    .data_bus_i    (wr_data_i),
    .data_bus_o    (wram_rd_data),
    .data_bus_oe_o (wram_rd_data_oe)
    );

    
    //izlazi ka CPU-u
    assign ready_o = (state_reg == DONE);

    // wram_rd_data_oe je 1 tacno u DONE taktu posle WRAM citanja.
    // Za ne-WRAM adrese za sada vracamo 00 (kasnije: open bus).
    assign rd_data_o = wram_rd_data_oe ? wram_rd_data : 8'h00;

endmodule