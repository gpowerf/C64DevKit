"""Tests for the VICE monitor response parsers (vice_bridge).

The parsers must survive the response pollution the real VICE text
monitor produces: breakpoint-stop preambles, disassembly lines, dump
rows of 16 or 32 bytes, and ASCII columns that can render hex-looking
character pairs.
"""

from c64devk.vice_bridge import _parse_memory_dump, _parse_registers


# --- Real-world capture: the first read after a breakpoint stop ---
# The stop message and a disassembly line precede the dump.  The old
# token-scanner grabbed the "AD" opcode from the disassembly instead
# of the memory byte.
RESP_AFTER_BREAKPOINT = (
    "#1 (Stop on  exec 0f16)   24/$018,  26/$1a\n"
    ".C:0f16  AD 31 0E    LDA $0E31      - A:10 X:00 Y:01 SP:f2 "
    "..-....C    6409394\n"
    "(C:$0f16) >C:0e67  00 00 \n"
    "(C:$0f16)"
)


def test_dump_ignores_breakpoint_preamble():
    assert _parse_memory_dump(RESP_AFTER_BREAKPOINT, 0x0E67, 1) == b"\x00"
    assert _parse_memory_dump(RESP_AFTER_BREAKPOINT, 0x0E67, 2) == b"\x00\x00"


def test_dump_combined_prompt_and_dump_line():
    resp = "(C:$0f16) >C:0e67  00 00 11 22\n"
    assert _parse_memory_dump(resp, 0x0E67, 4) == b"\x00\x00\x11\x22"


def test_dump_ascii_column_with_hex_looking_chars():
    # 16 real bytes, ASCII column renders printable "ab" — must not
    # be parsed as a 17th byte.
    hexblock = " ".join(f"{b:02x}" for b in range(16))
    resp = f">C:2000  {hexblock}   ........ab."
    assert _parse_memory_dump(resp, 0x2000, 16) == bytes(range(16))


def test_dump_multi_row_16_byte_rows():
    rows = []
    for i in range(2):
        addr = 0x2000 + i * 16
        hexblock = " ".join(f"{(i * 16 + b) & 0xFF:02x}" for b in range(16))
        rows.append(f">C:{addr:04x}  {hexblock}   ................")
    resp = "\n".join(rows)
    expected = bytes(range(32))
    assert _parse_memory_dump(resp, 0x2000, 32) == expected
    assert _parse_memory_dump(resp, 0x2000, 20) == expected[:20]


def test_dump_multi_row_32_byte_rows():
    rows = []
    for i in range(2):
        addr = 0x2000 + i * 32
        hexblock = " ".join(f"{(i * 32 + b) & 0xFF:02x}" for b in range(32))
        rows.append(f">C:{addr:04x}  {hexblock}   ................................")
    resp = "\n".join(rows)
    expected = bytes(range(64))
    assert _parse_memory_dump(resp, 0x2000, 64) == expected
    assert _parse_memory_dump(resp, 0x2000, 48) == expected[:48]


def test_dump_empty_response():
    assert _parse_memory_dump("", 0x2000, 4) == b""
    assert _parse_memory_dump("no dump here", 0x2000, 4) == b""


# --- Real-world capture: `r` command on this VICE build ---
RESP_REGISTERS = (
    "(C:$e5d1)   ADDR A  X  Y  SP 00 01 NV-BDIZC LIN CYC  STOPWATCH\n"
    ".;e5d1 00 01 55 f3 2f 37 00100010 000 000  999016200\n"
    "(C:$e5d1)"
)


def test_registers_current_format():
    regs = _parse_registers(RESP_REGISTERS)
    assert regs["PC"] == 0xE5D1
    assert regs["A"] == 0x00
    assert regs["X"] == 0x01
    assert regs["Y"] == 0x55
    assert regs["SP"] == 0xF3


def test_registers_legacy_token_format():
    regs = _parse_registers("PC=0810 A=00 X=42\n")
    assert regs["PC"] == 0x0810
    assert regs["X"] == 0x42
