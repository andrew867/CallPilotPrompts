#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the portable codec to the pinned NMCODEC build."""

import argparse
from collections import defaultdict
import ctypes
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import re
import struct
import zipfile

from extract_callpilot5 import Decoder
from nortel_sbc import Codec, PADDED_BLOCK_BYTES, parse_blocks

ENCODER_RVA = 0xDFF0


def encoder_vectors():
    for n in (240, 241, 255, 256, 257, 271, 272, 511, 512, 513, 752, 768, 769,
              1024, 7987, 8192, 16384, 27647, 27648, 27649, 27888, 32768):
        yield f"noise:{n}", random.Random(n).randbytes(2 * n)
    for n in (240, 256, 257, 512, 520, 1024, 27648, 28000):
        yield f"silence:{n}", bytes(2 * n)
        yield f"alternating:{n}", (b"\x00\x80\xff\x7f" * n)[:2 * n]
        yield f"sine:{n}", struct.pack(f"<{n}h", *(round(24000 * math.sin(math.tau * 701 * i / 8000))
                                                for i in range(n)))
    for i in (0, 15, 16, 31, 32, 224, 225, 238, 239, 240, 254, 255, 256, 257, 511, 512):
        yield f"impulse:{i}", bytes(2 * i) + b"\xff\x7f" + bytes(2 * (1023 - i))


def verify_encoder(native, portable):
    abi = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    encode = abi(native.dll._handle + ENCODER_RVA)
    count = 0
    for name, pcm in encoder_vectors():
        source = ctypes.create_string_buffer(pcm)
        # These bounded test inputs fit in two native output slots.
        target = ctypes.create_string_buffer(2 * PADDED_BLOCK_BYTES)
        length = ctypes.c_uint32()
        status = encode(source, len(pcm), target, ctypes.byref(length))
        if status or not 0 < length.value <= len(target):
            raise ValueError(f"NMCODEC encoder returned {status} and {length.value} bytes for {name}")
        if portable.encode(pcm, padded=True) != target.raw[:length.value]:
            raise ValueError(f"SBC bytes differ for encoder vector {name}")
        count += 1
    print(json.dumps({"encoder_vectors_matched": count}), flush=True)


def verify(archive, native, portable, locales):
    by_locale = defaultdict(list)
    for member in archive.infolist():
        match = re.search(r"/lang(\d+)/prompt/voice/\d+$", member.filename, re.IGNORECASE)
        if match and (not locales or int(match[1]) in locales):
            by_locale[int(match[1])].append(member)
    if not by_locale or locales - by_locale.keys():
        raise ValueError("No numbered prompts for the requested locales")

    checked = set()
    for locale, members in sorted(by_locale.items()):
        report = dict(locale=locale, files=len(members), playable=0, blocks=0, pcm_frames=0)
        for member in members:
            data = archive.read(member)
            report["playable"] += bool(data)
            for index, (block, frames) in enumerate(parse_blocks(data)):
                report["blocks"] += 1
                report["pcm_frames"] += frames
                digest = sha256(block).digest()
                if digest in checked:
                    continue
                if native.decode(block) != portable.decode(block):
                    raise ValueError(f"PCM differs for {member.filename}, block {index}")
                checked.add(digest)
        print(json.dumps(report), flush=True)
    print(json.dumps({"locales": len(by_locale), "distinct_blocks_compared": len(checked)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language_cd_zip", type=Path, nargs="?", help="optionally compare all prompts in this CD")
    parser.add_argument("--codec", required=True, type=Path, help="pinned 32-bit NMCODEC.DLL")
    parser.add_argument("--library", required=True, type=Path, help="compiled 32-bit portable SBC library")
    parser.add_argument("--locale", type=int, action="append", help="limit to this numeric locale ID")
    args = parser.parse_args()
    if args.locale and not args.language_cd_zip:
        parser.error("--locale requires a language CD ZIP")
    try:
        native, portable = Decoder(args.codec), Codec(args.library)
        verify_encoder(native, portable)
        if args.language_cd_zip:
            with zipfile.ZipFile(args.language_cd_zip) as archive:
                verify(archive, native, portable, set(args.locale or ()))
    except (AttributeError, OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
