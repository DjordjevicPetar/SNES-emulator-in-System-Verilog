module cartridge_memory (
  input  logic [1:0]  map_mode_i,
  input  logic [23:0] addr_i,

  output logic        wram_sel_o,
  output logic [16:0] wram_addr_o,

  output logic        io_sel_o,
  output logic [15:0] io_addr_o,

  output logic        sram_sel_o,
  output logic [18:0] sram_addr_o,

  output logic        rom_sel_o,
  output logic [22:0] rom_addr_o
);

  localparam logic [1:0] MAP_LOROM    = 2'd0;
  localparam logic [1:0] MAP_HIROM    = 2'd1;
  localparam logic [1:0] MAP_EXHIROM  = 2'd2;

  logic [7:0]  bank_id;
  logic [15:0] offset;

  logic full_wram;
  logic lorom_sram_sel;
  logic lorom_rom_sel;
  logic hirom_sram_sel;
  logic exhirom_sram_sel;
  logic hirom_rom_sel;

  assign bank_id = addr_i[23:16];
  assign offset = addr_i[15:0];

  // The console-side WRAM and I/O map is the same for every cartridge mapper.
  assign full_wram = bank_id == 8'h7e || bank_id == 8'h7f;

  assign wram_sel_o = (bank_id < 8'h40 && offset < 16'h2000) ||
                      (bank_id >= 8'h80 && bank_id < 8'hc0 && offset < 16'h2000) ||
                      full_wram;

  assign wram_addr_o = full_wram ? {bank_id[0], offset} : {4'b0000, offset[12:0]};

  assign io_sel_o = (bank_id < 8'h40 && offset >= 16'h2000 && offset < 16'h6000) ||
                    (bank_id >= 8'h80 && bank_id < 8'hc0 &&
                     offset >= 16'h2000 && offset < 16'h6000);

  assign io_addr_o = offset;

  // Mapper-specific chip-select equations.
  assign lorom_sram_sel = (((bank_id >= 8'h70 && bank_id < 8'h7e) ||
                            bank_id >= 8'hf0) && offset < 16'h8000);

  assign lorom_rom_sel = (((bank_id < 8'h7e || bank_id >= 8'h80) &&
                           offset >= 16'h8000) ||
                          (((bank_id >= 8'h40 && bank_id < 8'h70) ||
                            (bank_id >= 8'hc0 && bank_id < 8'hf0)) &&
                           offset < 16'h8000));

  assign hirom_sram_sel = (((bank_id >= 8'h30 && bank_id < 8'h40) ||
                            (bank_id >= 8'hb0 && bank_id < 8'hc0)) &&
                           offset >= 16'h6000 && offset < 16'h8000);

  assign exhirom_sram_sel = (bank_id >= 8'hb0 && bank_id < 8'hc0 &&
                             offset >= 16'h6000 && offset < 16'h8000);

  assign hirom_rom_sel = (((bank_id < 8'h7e || bank_id >= 8'h80) &&
                           offset >= 16'h8000) ||
                          (((bank_id >= 8'h40 && bank_id < 8'h7e) ||
                            bank_id >= 8'hc0) && offset < 16'h8000));

  always_comb begin
    sram_sel_o = 1'b0;
    sram_addr_o = '0;
    rom_sel_o = 1'b0;
    rom_addr_o = '0;

    unique case (map_mode_i)
      MAP_LOROM: begin
        sram_sel_o = lorom_sram_sel;
        sram_addr_o = {bank_id[3:0], offset[14:0]};
        rom_sel_o = lorom_rom_sel;
        rom_addr_o = {1'b0, bank_id[6:0], offset[14:0]};
      end

      MAP_HIROM: begin
        sram_sel_o = hirom_sram_sel;
        sram_addr_o = {2'b00, bank_id[3:0], offset[12:0]};
        rom_sel_o = hirom_rom_sel;
        rom_addr_o = {1'b0, bank_id[5:0], offset};
      end

      MAP_EXHIROM: begin
        sram_sel_o = exhirom_sram_sel;
        sram_addr_o = {2'b00, bank_id[3:0], offset[12:0]};
        rom_sel_o = hirom_rom_sel;
        rom_addr_o = {!bank_id[7], bank_id[5:0], offset};
      end

      default: begin
        sram_sel_o = 1'b0;
        sram_addr_o = '0;
        rom_sel_o = 1'b0;
        rom_addr_o = '0;
      end
    endcase
  end

endmodule
