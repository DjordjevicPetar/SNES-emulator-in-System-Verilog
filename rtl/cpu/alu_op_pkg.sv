package alu_op_pkg;

    typedef enum logic [7:0] {
        // Arithmetic
        ALU_OP_ADD = 8'b00000000,
        ALU_OP_SUB = 8'b00000001,
        ALU_OP_ADC = 8'b00000010,
        ALU_OP_SBC = 8'b00000011,
        // Logical
        ALU_OP_AND = 8'b00000100,
        ALU_OP_OR = 8'b00000101,
        ALU_OP_XOR = 8'b00000110,
        // Shift
        ALU_OP_ASL = 8'b00000111,
        ALU_OP_LSR = 8'b00001000,
        // Rotate
        ALU_OP_ROL = 8'b00001001,
        ALU_OP_ROR = 8'b00001010

    } alu_op_t;

endpackage
