#!/usr/bin/env python3
"""Extract audio elements from Nortel BCM 4.0 IVR MMF V3 pairs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_bcm4 import FORMATS, SAMPLE_RATE, alaw_conversion_table, write_audio

U32 = struct.Struct(">I")
AUDIO_KIND = 0x30
MULAW_CODEC = 4
PAGE_TABLE_START = 0xd8
INVERT = bytes(range(255, -1, -1))


def word(data, offset):
    return U32.unpack_from(data, offset)[0]


def read_elements(data):
    if len(data) < 0x50 or data[:4] != bytes.fromhex("11223344") or b"MMF V3" not in data[:0x34]:
        raise ValueError("Expected an MMF V3 .mmi header")
    stride = word(data, 0x34)
    table = word(data, 0x3c)
    if stride != 0x400 or table != 0x2000 or table > len(data) or (len(data) - table) % stride:
        raise ValueError("Invalid element table geometry")
    seen = set()
    for offset in range(table + stride, len(data), stride):
        record = data[offset:offset + stride]
        element_id, kind = struct.unpack_from(">II", record)
        if not kind:
            continue
        if element_id in seen:
            raise ValueError(f"Duplicate element ID {element_id}")
        seen.add(element_id)
        name_length = word(record, 0x28)
        if 0x30 + name_length > PAGE_TABLE_START:
            raise ValueError(f"Element {element_id} has an out-of-bounds name")
        name = record[0x30:0x30 + name_length].decode("latin-1")
        yield offset, element_id, kind, name, record


def read_payload(stream, record, size, page_size, element_id):
    length = word(record, 0x2c)
    page_count = (length + page_size - 1) // page_size
    if not length or PAGE_TABLE_START + page_count * U32.size > len(record):
        raise ValueError(f"Element {element_id} has an invalid payload length")
    page_offsets = [word(record, PAGE_TABLE_START + i * U32.size) for i in range(page_count)]
    payload = bytearray()
    for offset in page_offsets:
        if offset < page_size or offset % page_size or offset + page_size > size:
            raise ValueError(f"Element {element_id} points outside the data pages")
        expected = min(page_size, length - len(payload))
        stream.seek(offset)
        page = stream.read(expected)
        if len(page) != expected:
            raise ValueError(f"Element {element_id} has a truncated data page")
        payload.extend(page)
    return bytes(payload), page_offsets


def extract(index_path, output, formats):
    data_path = index_path.with_suffix(".mmd")
    if output.exists() or output.is_symlink():
        raise ValueError(f"{output} already exists. Choose a fresh output directory.")
    index = index_path.read_bytes()
    elements = list(read_elements(index))
    size = data_path.stat().st_size
    alaw_table = alaw_conversion_table() if "alaw" in formats else None
    output.parent.mkdir(parents=True, exist_ok=True)
    with data_path.open("rb") as source, tempfile.TemporaryDirectory(prefix=".mmf-", dir=output.parent) as temp_dir:
        header = source.read(0x44)
        if len(header) != 0x44 or header[:4] != bytes.fromhex("55667788"):
            raise ValueError("Expected the paired MMF .mmd data file")
        page_size = word(header, 0x40)
        if page_size != 0x2000 or size % page_size:
            raise ValueError("Invalid MMF data page geometry")
        source.seek(0)
        summary = {
            "source_name": index_path.stem,
            "mmi_sha256": hashlib.sha256(index).hexdigest(),
            "mmd_sha256": hashlib.file_digest(source, "sha256").hexdigest(),
            "mulaw_sample_rate": SAMPLE_RATE,
            "elements": len(elements),
            "mulaw": 0,
            "unconverted_audio": 0,
            "formats": list(formats),
        }
        staged = Path(temp_dir) / "prompts"
        staged.mkdir()
        audio = staged / "audio"
        if formats:
            audio.mkdir()

        with (staged / "elements.csv").open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["element_id", "index_offset", "kind", "name", "format_marker", "codec_id",
                             "bytes", "page_offsets", "source_sha256", "ulaw_sha256", "pcm_sha256", "status"])
            for offset, element_id, kind, name, record in elements:
                if kind != AUDIO_KIND:
                    writer.writerow([element_id, offset, f"0x{kind:02x}", name, "", "", "", "", "", "", "", "metadata"])
                    continue
                marker, codec = struct.unpack_from(">II", record, 0x20)
                payload, page_offsets = read_payload(source, record, size, page_size, element_id)
                filename = f"eap_{element_id:04d}"
                ulaw_hash = pcm_hash = ""
                if codec == MULAW_CODEC and marker == 0x10004:
                    raw = payload.translate(INVERT)
                    ulaw_hash = hashlib.sha256(raw).hexdigest()
                    summary["mulaw"] += 1
                    if formats:
                        pcm_hash = write_audio(audio, filename, raw, formats, alaw_table)
                    status = "exported" if formats else "indexed"
                else:
                    summary["unconverted_audio"] += 1
                    if formats:
                        (audio / f"{filename}.bin").write_bytes(payload)
                    status = "unconverted_codec"
                writer.writerow([element_id, offset, f"0x{kind:02x}", name, f"0x{marker:05x}", codec,
                                 len(payload), " ".join(map(str, page_offsets)), hashlib.sha256(payload).hexdigest(),
                                 ulaw_hash, pcm_hash, status])
        (staged / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        staged.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="Path to the .mmi, with the .mmd beside it")
    parser.add_argument("output", type=Path, help="New output directory")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--format", choices=FORMATS, action="append", help="Repeat to select formats (default: all three)")
    modes.add_argument("--index-only", action="store_true", help="Export metadata without writing audio")
    args = parser.parse_args()
    formats = () if args.index_only else tuple(dict.fromkeys(args.format or FORMATS))
    try:
        summary = extract(args.index, args.output, formats)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"{summary['mulaw']} mu-law elements, {summary['unconverted_audio']} other audio elements in {args.output}")


if __name__ == "__main__":
    main()
