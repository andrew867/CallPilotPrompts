#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Encode and decode Nortel CallPilot SBC with the portable C codec."""

import argparse
from array import array
import ctypes
import hashlib
from pathlib import Path
import struct
import sys
import wave

SAMPLE_RATE = 8000
PADDED_BLOCK_BYTES = 8192


def parse_blocks(data):
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError(f"Truncated block at {offset}")
        size = struct.unpack_from("<H", data, offset)[0]
        if not 154 <= size <= 8176 or size % 150 not in (4, 76) or offset + size > len(data):
            raise ValueError(f"Invalid block length {size} at {offset}")
        block = data[offset:offset + size]
        if block[2:7] != bytes(5) or block[7] not in (0x4e, 0x96) or any(block[-66:]):
            raise ValueError(f"Unexpected SBC framing at {offset}")
        yield block, (size - 76) // 75 * 256
        offset += size


def parse_padded_blocks(data):
    if len(data) % PADDED_BLOCK_BYTES:
        raise ValueError("truncated 8192-byte SBC block")
    for offset in range(0, len(data), PADDED_BLOCK_BYTES):
        slot = data[offset:offset + PADDED_BLOCK_BYTES]
        size = int.from_bytes(slot[:2], "little")
        if not 154 <= size <= 8176 or any(slot[size:]):
            raise ValueError(f"Invalid SBC block size or padding at {offset}")
        yield from parse_blocks(slot[:size])


class Codec:
    """Portable backend for the archived 18 kbit/s logical block stream."""

    def __init__(self, library):
        path = Path(library).resolve()
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.library = ctypes.CDLL(str(path))
        short_pointer = ctypes.POINTER(ctypes.c_int16)
        self.decode_block = self.library.nortel_sbc_decode_block
        self.decode_block.argtypes = (ctypes.c_char_p, ctypes.c_size_t, short_pointer, ctypes.c_size_t)
        self.decode_block.restype = ctypes.c_int
        self.encoded_size = self.library.nortel_sbc_encoded_size
        self.encoded_size.argtypes = (ctypes.c_size_t,)
        self.encoded_size.restype = ctypes.c_size_t
        self.encode_stream = self.library.nortel_sbc_encode
        self.encode_stream.argtypes = (short_pointer, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
        self.encode_stream.restype = ctypes.c_size_t

    def decode(self, data, *, padded=False):
        pcm = bytearray()
        blocks = parse_padded_blocks(data) if padded else parse_blocks(data)
        for block, frames in blocks:
            samples = (ctypes.c_int16 * frames)()
            actual = self.decode_block(block, len(block), samples, frames)
            if actual != frames:
                raise ValueError(f"Unsupported or invalid SBC block at frame {len(pcm) // 2}")
            if sys.byteorder == "little":
                pcm.extend(bytes(samples))
            else:
                words = array("h", samples)
                words.byteswap()
                pcm.extend(words.tobytes())
        return bytes(pcm)

    def encode(self, pcm, *, padded=False):
        if len(pcm) % 2:
            raise ValueError("truncated signed 16-bit PCM sample")
        frames = len(pcm) // 2
        capacity = self.encoded_size(frames)
        if not capacity:
            raise ValueError("SBC encoding requires at least 240 PCM samples")
        if sys.byteorder != "little":
            words = array("h")
            words.frombytes(pcm)
            words.byteswap()
            pcm = words.tobytes()
        native_pcm = (ctypes.c_int16 * frames).from_buffer_copy(pcm)
        output = ctypes.create_string_buffer(capacity)
        written = self.encode_stream(native_pcm, frames, output, capacity)
        if capacity != written:
            raise ValueError("SBC encoder did not produce the expected logical block length")
        if padded:
            return b"".join(block.ljust(PADDED_BLOCK_BYTES, b"\0") for block, _ in parse_blocks(output.raw))
        return output.raw


def read_wave(path):
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError("input must be 8 kHz, mono, signed 16-bit PCM WAV")
        frames = source.getnframes()
        pcm = source.readframes(frames)
        if len(pcm) != 2 * frames:
            raise ValueError("truncated input WAV")
        return pcm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("encode", "decode"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--library", type=Path, required=True, help="compiled portable SBC shared library")
    parser.add_argument("--padded-blocks", action="store_true", help="use 8192-byte DLL buffer slots for the SBC stream")
    args = parser.parse_args()
    try:
        codec = Codec(args.library)
        if args.operation == "encode":
            stream = codec.encode(read_wave(args.source), padded=args.padded_blocks)
            with args.output.open("xb") as target:
                target.write(stream)
        else:
            pcm = codec.decode(args.source.read_bytes(), padded=args.padded_blocks)
            with args.output.open("xb") as target, wave.open(target, "wb") as wav:
                wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
    except (AttributeError, EOFError, OSError, ValueError, wave.Error) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
