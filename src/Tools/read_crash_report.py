#!/usr/bin/env python3
"""Print a .fcrash file written by the crash reporter.

The reporter drops a binary report next to its minidump, under

    %APPDATA%/OtherCAD/<version>/CrashReports/

and the exception code alone usually says what happened: a null dereference
reads 0xc0000005 with a fault address of 0, whereas a failed assertion reads
0xc0000409. The frames are module plus offset; without .pdb files they will not
resolve to function names, but knowing which library faulted is normally enough
to place the fault.

    python src/Tools/read_crash_report.py <path-to-.fcrash>
    python src/Tools/read_crash_report.py --latest

Layout is defined by src/Base/CrashReporter/Format.h: a 128-byte header, then a
table of 24-byte frames, then length-prefixed strings.
"""

import argparse
import datetime
import glob
import os
import struct
import sys

MAGIC = 0x52434346  # 'FCCR'
NO_STRING = 0xFFFFFFFF

EXCEPTION_CODES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC0000006: "IN_PAGE_ERROR",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION",
    0xC0000026: "INVALID_DISPOSITION",
    0xC000008C: "ARRAY_BOUNDS_EXCEEDED",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000374: "HEAP_CORRUPTION",
    0xC0000409: "STACK_BUFFER_OVERRUN (__fastfail, often a failed assertion)",
    0x80000003: "BREAKPOINT",
    0xE06D7363: "C++ exception (MSVC throw)",
}

OS_NAMES = {0: "none", 1: "Linux", 2: "macOS", 3: "Windows", 4: "BSD"}
ARCH_NAMES = {0: "none", 1: "x64", 2: "aarch64"}
FLAG_NAMES = {1: "has-minidump", 2: "partial-write", 4: "signal-safe-capture"}


def read_string_table(blob, offset):
    """uint16 length then that many bytes, keyed by offset from the table start.

    The first record is empty, so a reader that stops at a zero length finds
    nothing at all.
    """
    table = {}
    pos = offset
    while pos + 2 <= len(blob):
        (length,) = struct.unpack_from("<H", blob, pos)
        if pos + 2 + length > len(blob):
            break
        table[pos - offset] = blob[pos + 2 : pos + 2 + length].decode(
            "utf-8", errors="replace"
        )
        pos += 2 + length
    return table


def find_latest():
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), "OtherCAD"),
        os.path.join(os.environ.get("APPDATA", ""), "FreeCAD"),
        os.path.expanduser("~/.local/share/OtherCAD"),
        os.path.expanduser("~/.local/share/FreeCAD"),
    ]
    found = []
    for root in roots:
        if root and os.path.isdir(root):
            found += glob.glob(os.path.join(root, "**", "*.fcrash"), recursive=True)
    return max(found, key=os.path.getmtime) if found else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="the .fcrash file to read")
    parser.add_argument("--latest", action="store_true",
                        help="read the most recent report in the user data directory")
    args = parser.parse_args()

    path = args.path
    if args.latest or not path:
        path = find_latest()
        if not path:
            sys.exit("no .fcrash reports found")

    with open(path, "rb") as handle:
        blob = handle.read()

    magic, version = struct.unpack_from("<II", blob, 0)
    if magic != MAGIC:
        sys.exit(f"{path} is not a crash report (magic {magic:#x})")

    fault, thread, timestamp = struct.unpack_from("<QQq", blob, 8)
    pid, code, frame_count, _size, flags = struct.unpack_from("<IIIII", blob, 32)
    frame_offset, string_offset = struct.unpack_from("<II", blob, 52)
    build_off, suffix_off, dump_off, message_off = struct.unpack_from("<IIII", blob, 60)
    os_id, arch_id, major, minor, patch = struct.unpack_from("<BBBBB", blob, 76)

    strings = read_string_table(blob, string_offset)

    def text(offset):
        return strings.get(offset, "") if offset != NO_STRING else ""

    when = datetime.datetime.fromtimestamp(timestamp).isoformat(" ", "seconds")
    set_flags = [name for bit, name in FLAG_NAMES.items() if flags & bit] or ["none"]

    print(f"report    : {path}")
    print(f"written   : {when}   (format v{version})")
    print(f"version   : {major}.{minor}.{patch}{text(suffix_off)}   build {text(build_off)}")
    print(f"platform  : {OS_NAMES.get(os_id, os_id)} / {ARCH_NAMES.get(arch_id, arch_id)}")
    print(f"process   : pid {pid}, faulting thread {thread}")
    print(f"exception : {code:#010x}  {EXCEPTION_CODES.get(code, 'unrecognised')}")
    print(f"address   : {fault:#018x}"
          + ("   (null dereference)" if fault == 0 else ""))
    print(f"flags     : {', '.join(set_flags)}")
    if message_off != NO_STRING:
        print(f"message   : {text(message_off)}")
    if dump_off != NO_STRING:
        print(f"minidump  : {text(dump_off)}")

    print(f"\nframes    : {frame_count}, innermost first")
    for index in range(frame_count):
        start = frame_offset + index * 24
        if start + 24 > len(blob):
            break
        raw, module_offset, module_string, _pad = struct.unpack_from("<QQII", blob, start)
        module = text(module_string) or "?"
        name = module.replace("\\", "/").rsplit("/", 1)[-1]
        print(f"  #{index:<3} {name:<34} +{module_offset:#012x}   ({raw:#018x})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
