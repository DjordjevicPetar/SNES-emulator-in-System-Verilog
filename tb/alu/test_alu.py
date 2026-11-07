"""Tests for binary ADD, SUB, ADC, SBC, AND, OR, XOR, ASL, LSR, ROL and ROR.

SUB computes A - B. Its carry output follows the intended 65C816 CPU flag:
C = 1 means no borrow (A >= B), while C = 0 means a borrow was needed.
In 8-bit mode the upper input bytes are ignored and result_o is zero-extended.
ADD/SUB are plain binary operations, without carry-in or decimal mode.
ADC computes A + B + carry_i. SBC computes A - B - (1 - carry_i), with
C = 1 meaning no borrow. Decimal/BCD mode is not part of this test contract.
ROL/ROR rotate through the OLD carry_i; they are not circular operand rotates.

Only meaningful flag outputs are checked: ADD/SUB/ADC/SBC produce N/Z/C/V, logical
operations produce N/Z, and shifts/rotates produce N/Z/C. None in an expected
output tuple means that the CPU must not use that flag for the operation.
Preserving CPU status register bits belongs to the CPU, not this ALU.

Operation encodings come from rtl/cpu/alu_op_pkg.sv. This testbench is
combinational: drive inputs, allow propagation, then sample all five outputs.
"""

import random
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import cocotb
from cocotb.triggers import Timer


OPERATIONS = {
    "ADD": 0,
    "SUB": 1,
    "ADC": 2,
    "SBC": 3,
    "AND": 4,
    "OR": 5,
    "XOR": 6,
    "ASL": 7,
    "LSR": 8,
    "ROL": 9,
    "ROR": 10,
}
BINARY_OPERATIONS = ("ADD", "SUB", "ADC", "SBC", "AND", "OR", "XOR")
UNARY_OPERATIONS = ("ASL", "LSR", "ROL", "ROR")
ROTATIONS = ("ROL", "ROR")
CARRY_ARITHMETIC = ("ADC", "SBC")
CARRY_OPERATIONS = CARRY_ARITHMETIC + ROTATIONS
OUTPUTS = ("result_o", "negative_o", "zero_o", "carry_o", "overflow_o")


@dataclass(frozen=True)
class AluCase:
    operation: str
    width: int
    a: int
    b: int = 0
    carry: int = 0
    expected: Optional[tuple] = None

# Each row is (A, B, (result, N, Z, C, V)). These examples are hand-calculated
# so that the directed tests do not depend on the Python arithmetic model.
EXAMPLES = {
    ("ADD", 8, 0): (
        (0x00, 0x00, (0x00, 0, 1, 0, 0)),
        (0x01, 0x02, (0x03, 0, 0, 0, 0)),
        (0x7F, 0x01, (0x80, 1, 0, 0, 1)),
        (0xFF, 0x01, (0x00, 0, 1, 1, 0)),
        (0x80, 0x80, (0x00, 0, 1, 1, 1)),
        (0xFF, 0xFF, (0xFE, 1, 0, 1, 0)),
        (0x7F, 0x80, (0xFF, 1, 0, 0, 0)),
        (0x80, 0x00, (0x80, 1, 0, 0, 0)),
    ),
    ("ADD", 16, 0): (
        (0x0000, 0x0000, (0x0000, 0, 1, 0, 0)),
        (0x00FF, 0x0001, (0x0100, 0, 0, 0, 0)),
        (0x7FFF, 0x0001, (0x8000, 1, 0, 0, 1)),
        (0xFFFF, 0x0001, (0x0000, 0, 1, 1, 0)),
        (0x8000, 0x8000, (0x0000, 0, 1, 1, 1)),
        (0xFFFF, 0xFFFF, (0xFFFE, 1, 0, 1, 0)),
        (0x7FFF, 0x8000, (0xFFFF, 1, 0, 0, 0)),
        (0x8000, 0x0000, (0x8000, 1, 0, 0, 0)),
    ),
    ("SUB", 8, 0): (
        (0x00, 0x00, (0x00, 0, 1, 1, 0)),
        (0x03, 0x02, (0x01, 0, 0, 1, 0)),
        (0x00, 0x01, (0xFF, 1, 0, 0, 0)),
        (0x80, 0x01, (0x7F, 0, 0, 1, 1)),
        (0x7F, 0xFF, (0x80, 1, 0, 0, 1)),
        (0xFF, 0x01, (0xFE, 1, 0, 1, 0)),
        (0x80, 0x80, (0x00, 0, 1, 1, 0)),
        (0x00, 0x80, (0x80, 1, 0, 0, 1)),
    ),
    ("SUB", 16, 0): (
        (0x0000, 0x0000, (0x0000, 0, 1, 1, 0)),
        (0x0100, 0x0001, (0x00FF, 0, 0, 1, 0)),
        (0x0000, 0x0001, (0xFFFF, 1, 0, 0, 0)),
        (0x8000, 0x0001, (0x7FFF, 0, 0, 1, 1)),
        (0x7FFF, 0xFFFF, (0x8000, 1, 0, 0, 1)),
        (0xFFFF, 0x0001, (0xFFFE, 1, 0, 1, 0)),
        (0x8000, 0x8000, (0x0000, 0, 1, 1, 0)),
        (0x0000, 0x8000, (0x8000, 1, 0, 0, 1)),
    ),
}


for width in (8, 16):
    mask = (1 << width) - 1
    msb = 1 << (width - 1)
    alternating_a = 0xAAAA & mask
    alternating_b = 0x5555 & mask

    # ADC with C=0 is ADD; SBC with C=1 is SUB. Reuse the independent
    # hand-calculated tables for these two exact equivalences.
    EXAMPLES["ADC", width, 0] = EXAMPLES["ADD", width, 0]
    EXAMPLES["SBC", width, 1] = EXAMPLES["SUB", width, 0]
    EXAMPLES["ADC", width, 1] = (
        (0, 0, (1, 0, 0, 0, 0)),
        (mask, 0, (0, 0, 1, 1, 0)),
        (msb - 1, 0, (msb, 1, 0, 0, 1)),
        (msb, msb - 1, (0, 0, 1, 1, 0)),
        (msb, msb, (1, 0, 0, 1, 1)),
        (mask, mask, (mask, 1, 0, 1, 0)),
        (msb - 1, msb - 1, (mask, 1, 0, 0, 1)),
        (0, mask, (0, 0, 1, 1, 0)),
        (msb, mask, (msb, 1, 0, 1, 0)),
    )
    EXAMPLES["SBC", width, 0] = (
        (0, 0, (mask, 1, 0, 0, 0)),
        (1, 0, (0, 0, 1, 1, 0)),
        (0, mask, (0, 0, 1, 0, 0)),
        (mask, mask, (mask, 1, 0, 0, 0)),
        (mask, 0, (mask - 1, 1, 0, 1, 0)),
        (msb, 0, (msb - 1, 0, 0, 1, 1)),
        (msb - 1, mask, (msb - 1, 0, 0, 0, 0)),
        (msb - 1, msb, (mask - 1, 1, 0, 0, 1)),
        (msb, msb, (mask, 1, 0, 0, 0)),
        (0, msb - 1, (msb, 1, 0, 0, 0)),
        (msb, mask, (msb, 1, 0, 0, 0)),
    )

    EXAMPLES["AND", width, 0] = (
        (0, mask, (0, 0, 1, None, None)),
        (mask, mask, (mask, 1, 0, None, None)),
        (alternating_a, alternating_b, (0, 0, 1, None, None)),
        (mask, 1, (1, 0, 0, None, None)),
        (mask, msb, (msb, 1, 0, None, None)),
        (msb - 1, mask, (msb - 1, 0, 0, None, None)),
    )
    EXAMPLES["OR", width, 0] = (
        (0, 0, (0, 0, 1, None, None)),
        (0, mask, (mask, 1, 0, None, None)),
        (alternating_a, alternating_b, (mask, 1, 0, None, None)),
        (msb, 1, (msb + 1, 1, 0, None, None)),
        (1, 2, (3, 0, 0, None, None)),
        (msb, msb, (msb, 1, 0, None, None)),
    )
    EXAMPLES["XOR", width, 0] = (
        (0, 0, (0, 0, 1, None, None)),
        (mask, mask, (0, 0, 1, None, None)),
        (alternating_a, alternating_b, (mask, 1, 0, None, None)),
        (msb, msb, (0, 0, 1, None, None)),
        (msb, 1, (msb + 1, 1, 0, None, None)),
        (mask, msb, (msb - 1, 0, 0, None, None)),
    )
    EXAMPLES["ASL", width, 0] = (
        (0, 0, (0, 0, 1, 0, None)),
        (1, 0, (2, 0, 0, 0, None)),
        (msb, 0, (0, 0, 1, 1, None)),
        (msb // 2, 0, (msb, 1, 0, 0, None)),
        (msb + 2, 0, (4, 0, 0, 1, None)),
        (mask, 0, (mask - 1, 1, 0, 1, None)),
    )
    EXAMPLES["LSR", width, 0] = (
        (0, 0, (0, 0, 1, 0, None)),
        (1, 0, (0, 0, 1, 1, None)),
        (2, 0, (1, 0, 0, 0, None)),
        (msb, 0, (msb // 2, 0, 0, 0, None)),
        (msb + 2, 0, (msb // 2 + 1, 0, 0, 0, None)),
        (mask, 0, (msb - 1, 0, 0, 1, None)),
    )
    EXAMPLES["ROL", width, 0] = EXAMPLES["ASL", width, 0]
    EXAMPLES["ROR", width, 0] = EXAMPLES["LSR", width, 0]
    EXAMPLES["ROL", width, 1] = (
        (0, 0, (1, 0, 0, 0, None)),
        (1, 0, (3, 0, 0, 0, None)),
        (msb, 0, (1, 0, 0, 1, None)),
        (msb // 2, 0, (msb + 1, 1, 0, 0, None)),
        (msb + 2, 0, (5, 0, 0, 1, None)),
        (mask, 0, (mask, 1, 0, 1, None)),
    )
    EXAMPLES["ROR", width, 1] = (
        (0, 0, (msb, 1, 0, 0, None)),
        (1, 0, (msb, 1, 0, 1, None)),
        (2, 0, (msb + 1, 1, 0, 0, None)),
        (msb, 0, (msb + msb // 2, 1, 0, 0, None)),
        (msb + 2, 0, (msb + msb // 2 + 1, 1, 0, 0, None)),
        (mask, 0, (mask, 1, 0, 1, None)),
    )


UNARY_CONFIGS = [
    (operation, width, carry)
    for operation in UNARY_OPERATIONS
    for width in (8, 16)
    for carry in ((0, 1) if operation in ROTATIONS else (0,))
]

BINARY_CONFIGS = [
    (operation, carry)
    for operation in BINARY_OPERATIONS
    for carry in ((0, 1) if operation in CARRY_ARITHMETIC else (0,))
]


def reference_result(operation, width, a, b, carry_in=0):
    """Use unbounded Python math and signed range checks, not RTL equations."""
    modulus = 1 << width
    sign_bit = modulus // 2
    a %= modulus
    b %= modulus
    signed_a = a if a < sign_bit else a - modulus
    signed_b = b if b < sign_bit else b - modulus

    carry = None
    overflow = None
    if operation in ("ADD", "ADC"):
        carry_addend = carry_in if operation == "ADC" else 0
        value = a + b + carry_addend
        signed_value = signed_a + signed_b + carry_addend
        carry = int(value >= modulus)
        overflow = int(not (-sign_bit <= signed_value < sign_bit))
    elif operation in ("SUB", "SBC"):
        borrow = 1 - carry_in if operation == "SBC" else 0
        value = a - b - borrow
        signed_value = signed_a - signed_b - borrow
        carry = int(value >= 0)
        overflow = int(not (-sign_bit <= signed_value < sign_bit))
    elif operation == "AND":
        value = a & b
    elif operation == "OR":
        value = a | b
    elif operation == "XOR":
        value = a ^ b
    elif operation == "ASL":
        value = a * 2
        carry = int(value >= modulus)
    elif operation == "LSR":
        value = a // 2
        carry = a % 2
    elif operation == "ROL":
        value = a * 2 + carry_in
        carry = int(value >= modulus)
    elif operation == "ROR":
        value = a // 2 + carry_in * sign_bit
        carry = a % 2
    else:
        raise ValueError(f"Unsupported ALU operation: {operation}")

    result = value % modulus
    negative = int(result >= sign_bit)
    zero = int(result == 0)
    return result, negative, zero, carry, overflow


async def evaluate(dut, case):
    carry_input = getattr(dut, "carry_i", None)
    if case.operation in CARRY_OPERATIONS:
        assert carry_input is not None, (
            f"{case.operation} requires an input port named carry_i "
            "for the previous CPU carry."
        )
    if carry_input is not None:
        carry_input.value = case.carry

    dut.op_i.value = OPERATIONS[case.operation]
    dut.is_16bit_i.value = int(case.width == 16)
    dut.a_i.value = case.a
    dut.b_i.value = case.b
    await Timer(1, unit="ns")
    return tuple(int(getattr(dut, output).value) for output in OUTPUTS)


async def check_cases(dut, cases):
    """Check every case even on failure; keep the error report short.

    AluCase.expected selects explicit outputs or the Python reference model.
    None flag values are deliberately ignored, not assumed to be cleared.
    """
    checked = 0
    failed = 0
    failures_by_output = Counter()
    examples = []

    for case in cases:
        expected = case.expected
        if expected is None:
            expected = reference_result(
                case.operation, case.width, case.a, case.b, case.carry
            )
        observed = await evaluate(dut, case)
        checked += 1

        differences = [
            f"{name}: expected {wanted:#x}, got {actual:#x}"
            for name, wanted, actual in zip(OUTPUTS, expected, observed)
            if wanted is not None and wanted != actual
        ]
        if differences:
            failed += 1
            failures_by_output.update(
                name
                for name, wanted, actual in zip(OUTPUTS, expected, observed)
                if wanted is not None and wanted != actual
            )
            if len(examples) < 4:
                examples.append(
                    f"{case.operation}/{case.width}: A={case.a:#06x}, "
                    f"B={case.b:#06x}, C_in={case.carry}: "
                    + "; ".join(differences)
                )

    dut._log.info(
        "Checked %d cases; failures=%d, mismatches by output=%s",
        checked,
        failed,
        dict(failures_by_output),
    )
    assert failed == 0, (
        f"{failed}/{checked} cases failed; "
        f"mismatches by output: {dict(failures_by_output)}\n"
        + "\n".join(examples)
    )


@cocotb.test()
@cocotb.parametrize((("operation", "width", "carry"), list(EXAMPLES)))
async def hand_calculated_results_and_flags(dut, operation, width, carry):
    await check_cases(
        dut,
        (
            AluCase(operation, width, a, b, carry, expected)
            for a, b, expected in EXAMPLES[operation, width, carry]
        ),
    )


@cocotb.test()
@cocotb.parametrize((("operation", "carry"), BINARY_CONFIGS))
async def all_eight_bit_operand_pairs(dut, operation, carry):
    await check_cases(
        dut,
        (
            AluCase(operation, 8, a, b, carry)
            for a in range(256)
            for b in range(256)
        ),
    )


@cocotb.test()
@cocotb.parametrize((("operation", "carry"), BINARY_CONFIGS))
async def sixteen_bit_boundaries_and_random_operands(dut, operation, carry):
    rng = random.Random(0x65816)
    boundaries = (
        0x0000, 0x0001, 0x007F, 0x0080, 0x00FF, 0x0100,
        0x7FFE, 0x7FFF, 0x8000, 0x8001, 0xFFFE, 0xFFFF,
    )
    pairs = [(a, b) for a in boundaries for b in boundaries]
    pairs.extend((rng.randrange(65536), rng.randrange(65536)) for _ in range(4096))

    await check_cases(
        dut,
        (AluCase(operation, 16, a, b, carry) for a, b in pairs),
    )


@cocotb.test()
@cocotb.parametrize(operation=list(OPERATIONS))
async def eight_bit_mode_ignores_upper_input_bytes(dut, operation):
    cases = []
    for carry in ((0, 1) if operation in CARRY_OPERATIONS else (0,)):
        for low_a, low_b, expected in EXAMPLES[operation, 8, carry]:
            for high_a, high_b in (
                (0x01, 0x00), (0x00, 0x80), (0xFF, 0xFF), (0x80, 0x7F),
            ):
                cases.append(
                    AluCase(
                        operation, 8, (high_a << 8) | low_a,
                        (high_b << 8) | low_b, carry, expected,
                    )
                )
    await check_cases(dut, cases)


@cocotb.test()
@cocotb.parametrize((("operation", "width", "carry"), UNARY_CONFIGS))
async def all_shift_and_rotate_operand_values(dut, operation, width, carry):
    # Unary operations have only 256/65536 operands, so even the 16-bit
    # domain can be tested completely, with both carry inputs for rotates.
    await check_cases(
        dut,
        (
            AluCase(operation, width, a, 0xA55A, carry)
            for a in range(1 << width)
        ),
    )


@cocotb.test()
@cocotb.parametrize(operation=UNARY_OPERATIONS, width=[8, 16])
async def shifts_and_rotates_ignore_b_operand(dut, operation, width):
    cases = []
    for carry in ((0, 1) if operation in ROTATIONS else (0,)):
        for a in (0, 1, 2, 0x7F, 0x80, 0x8000, 0xFFFF):
            for b in (0, 1, 0xFFFF, 0x5555, 0xAAAA):
                cases.append(AluCase(operation, width, a, b, carry))
    await check_cases(dut, cases)


@cocotb.test()
@cocotb.parametrize(operation=UNARY_OPERATIONS + CARRY_ARITHMETIC)
async def changing_only_carry_input_recomputes_result_and_flags(dut, operation):
    cases = []
    for width in (8, 16):
        for a in (0, 1, 2, 0x80, 0xFFFF):
            for carry in (0, 1, 0, 1):
                cases.append(AluCase(operation, width, a, 0xFFFF, carry))
    await check_cases(dut, cases)


@cocotb.test()
@cocotb.parametrize(operation=CARRY_ARITHMETIC)
async def two_eight_bit_operations_chain_to_a_sixteen_bit_result(dut, operation):
    # The ALU does not store carry: the caller forwards the low-byte carry
    # to the high-byte operation, exactly as a sequence of CPU instructions would.
    pairs = (
        (0x0000, 0x0000), (0x00FF, 0x0001), (0xFFFF, 0x0001),
        (0x7FFF, 0x0001), (0x8000, 0x0001), (0x0100, 0x0001),
        (0x0000, 0xFFFF), (0x8000, 0x8000), (0xFFFF, 0xFFFF),
        (0x1234, 0xABCD),
    )
    rng = random.Random(0xCA771)
    pairs += tuple((rng.randrange(65536), rng.randrange(65536)) for _ in range(256))
    cases = []
    for carry_in in (0, 1):
        for a, b in pairs:
            low_case = AluCase(operation, 8, a & 0xFF, b & 0xFF, carry_in)
            low = await evaluate(dut, low_case)
            high_case = AluCase(operation, 8, a >> 8, b >> 8, low[3])
            high = await evaluate(dut, high_case)
            expected = reference_result(operation, 16, a, b, carry_in)
            combined = (
                (high[0] << 8) | low[0],
                high[1],
                int(low[2] and high[2]),
                high[3],
                high[4],
            )
            cases.append((a, b, carry_in, expected, combined))

    failures = [
        f"{operation}/16 via two bytes: A={a:#06x}, B={b:#06x}, C_in={carry}: "
        f"expected {expected}, got {observed}"
        for a, b, carry, expected, observed in cases
        if expected != observed
    ]
    dut._log.info("Checked %d two-byte carry chains; failures=%d", len(cases), len(failures))
    assert not failures, f"{len(failures)}/{len(cases)} carry chains failed\n" + "\n".join(
        failures[:4]
    )


@cocotb.test()
async def switching_operation_and_width_does_not_retain_old_outputs(dut):
    # Reuse operands while changing one control input at a time, including
    # 16 -> 8 transitions that must clear the upper result byte.
    cases = []
    for a, b in (
        (0xFFFF, 0x0001), (0x8000, 0x0001), (0x007F, 0x0001),
        (0x0000, 0x0000), (0xAA80, 0x55FF), (0x1234, 0xABCD),
    ):
        for operation in OPERATIONS:
            for width, carry in ((16, 0), (8, 0), (8, 1), (16, 1)):
                cases.append(AluCase(operation, width, a, b, carry))
    await check_cases(dut, cases)
