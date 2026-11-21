#!/usr/bin/env python3
"""Decode the CallPilot 5.0 language CD's numbered prompts with Nortel's x86 SBC codec."""

import argparse
import csv
import ctypes
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
import wave
import zipfile

DLL_SHA256 = "c48eb80a73a91b268f78cafe8baffe0b8298ed28141a52fa71887058496be56d"
SBC_DECODE_RVA = 0xdf20
CODEC_BLOCK_BYTES = 8192
PCM_BUFFER_BYTES = 65536
SAMPLE_RATE = 8000
SOURCE_NAME = re.compile(r"Copied encoded file (\S+) to ([0-9]+)")


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


class Decoder:
    def __init__(self, path):
        if not hasattr(ctypes, "WinDLL") or ctypes.sizeof(ctypes.c_void_p) != 4:
            raise ValueError("Use 32-bit Windows Python with the documented NMCODEC.DLL")
        if hashlib.sha256(path.read_bytes()).hexdigest() != DLL_SHA256:
            raise ValueError("NMCODEC.DLL does not match the verified build")
        self.dll = ctypes.CDLL(str(path.resolve()))
        abi = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.POINTER(ctypes.c_uint32))
        self.decode_block = abi(self.dll._handle + SBC_DECODE_RVA)

    def decode(self, data):
        blocks = []
        for block, frames in parse_blocks(data):
            source = ctypes.create_string_buffer(block, CODEC_BLOCK_BYTES)
            output = ctypes.create_string_buffer(PCM_BUFFER_BYTES)
            samples = ctypes.c_uint32()
            status = self.decode_block(source, output, ctypes.byref(samples))
            if status or samples.value != frames:
                raise ValueError(f"SBC decoder returned {status} with {samples.value} frames, expected {frames}")
            blocks.append(output.raw[:2 * samples.value])
        return b"".join(blocks)


def locale_directory(archive, locale):
    candidates = [PurePosixPath(n).parent.parent for n in archive.namelist()
                  if n.endswith(f"/lang{locale}/prompt/data/langinfo.lng")]
    if len(candidates) != 1:
        raise ValueError(f"Expected one prompt directory for locale {locale}")
    return candidates[0]


def extract(source, output, locale, decoder):
    if output.exists() or output.is_symlink():
        raise ValueError(f"{output} already exists. Choose a fresh output directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory(dir=output.parent) as temp:
        base = locale_directory(archive, locale)
        staged = Path(temp) / "output"
        audio = staged / "audio"
        audio.mkdir(parents=True)
        metadata = staged / "data"
        metadata.mkdir()
        for name in ("langinfo.lng", "ExportLog.txt", "vtfa.v", "vtfb.v", "sceapp0.l", "sceapp0.m"):
            (metadata / name).write_bytes(archive.read(str(base / "data" / name)))
        log = (metadata / "ExportLog.txt").read_text(encoding="latin-1")
        original_names = {prompt: name for name, prompt in SOURCE_NAME.findall(log)}

        voices = []
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if not item.is_dir() and path.parent == base / "voice":
                if not re.fullmatch(r"[0-9]+", path.name):
                    raise ValueError(f"Unexpected voice file name {path.name}")
                voices.append((path.name, item))
        if not voices or len({name for name, _ in voices}) != len(voices):
            raise ValueError("No voice files or duplicate prompt IDs")

        exported = 0
        with (staged / "prompts.csv").open("w", encoding="utf-8", newline="") as report:
            csv_writer = csv.writer(report, lineterminator="\n")
            csv_writer.writerow(("voice_id", "source_name", "source_bytes", "source_sha256",
                                 "frames", "pcm_sha256", "wav", "status"))
            for voice_id, item in sorted(voices, key=lambda row: int(row[0])):
                data = archive.read(item)
                digest = hashlib.sha256(data).hexdigest()
                pcm = decoder.decode(data)
                wav = f"audio/{voice_id}.wav" if pcm else ""
                if pcm:
                    with wave.open(str(staged / wav), "wb") as target:
                        target.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                        target.writeframes(pcm)
                    exported += 1
                csv_writer.writerow((voice_id, original_names.get(voice_id, ""), len(data), digest,
                                     len(pcm) // 2, hashlib.sha256(pcm).hexdigest() if pcm else "",
                                     wav, "exported" if pcm else "empty"))
        summary = {"locale": locale, "directory": str(base), "voice_files": len(voices),
                   "exported": exported, "sample_rate": SAMPLE_RATE, "decoder_sha256": DLL_SHA256}
        (staged / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        staged.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language_cd_zip", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--codec", type=Path, required=True, help="Path to the verified 32-bit NMCODEC.DLL")
    parser.add_argument("--locale", type=int, default=4105, help="Windows locale ID (default: Canadian English)")
    args = parser.parse_args()
    try:
        summary = extract(args.language_cd_zip, args.output, args.locale, Decoder(args.codec))
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"{summary['exported']} of {summary['voice_files']} voice files exported")


if __name__ == "__main__":
    main()
