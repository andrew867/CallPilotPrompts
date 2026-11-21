#!/usr/bin/env python3
"""Export factory prompts from an extracted Nortel BCM 4.0 language directory."""

import argparse
import codecs
import csv
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave

SAMPLE_RATE = 8000
BANK_HEADER = struct.Struct("<6I")
PHRASE_ENTRY = struct.Struct("<III")
INDEX_ENTRY = struct.Struct("<IH")
TEMPLATE_FIELD = struct.Struct("<5H")
FORMATS = ("wav", "ulaw", "alaw")


def mulaw_sample(encoded):
    code = encoded ^ 0xff
    magnitude = ((code & 15) * 8 + 132) << ((code >> 4) & 7)
    return 132 - magnitude if code & 128 else magnitude - 132


MULAW_PCM = struct.pack("<256h", *(mulaw_sample(code) for code in range(256)))


def decode_mulaw(data):
    pcm = bytearray(len(data) * 2)
    pcm[::2] = data.translate(MULAW_PCM[::2])
    pcm[1::2] = data.translate(MULAW_PCM[1::2])
    return pcm


def alaw_conversion_table():
    command = shutil.which("ffmpeg")
    if command is None:
        raise ValueError("FFmpeg is required for A-law output. Use --format wav --format ulaw without it.")
    result = subprocess.run(
        [command, "-hide_banner", "-loglevel", "error", "-f", "mulaw", "-ar", str(SAMPLE_RATE),
         "-ac", "1", "-i", "pipe:0", "-c:a", "pcm_alaw", "-f", "alaw", "pipe:1"],
        input=bytes(range(256)), stdout=subprocess.PIPE, check=True,
    ).stdout
    if len(result) != 256:
        raise ValueError("FFmpeg produced an invalid G.711 conversion table")
    return result


def read_phrase_index(stream, size):
    header = stream.read(BANK_HEADER.size)
    if len(header) != BANK_HEADER.size:
        raise ValueError("Truncated phrase_s header")
    count, *reserved = BANK_HEADER.unpack(header)
    index_end = BANK_HEADER.size + count * PHRASE_ENTRY.size
    if not count or any(reserved) or index_end > size:
        raise ValueError("Unsupported phrase_s header or truncated index")

    entries = list(PHRASE_ENTRY.iter_unpack(stream.read(index_end - BANK_HEADER.size)))
    previous_end = index_end
    for index, (offset, length, field) in enumerate(entries):
        if field or offset != previous_end or offset + length > size:
            raise ValueError(f"Invalid or unsupported phrase_s index entry {index}")
        previous_end = offset + length
    if previous_end != size:
        raise ValueError("Unexpected data after the last phrase")
    return entries


def read_index(data, start, count, unit_size):
    table_end = start + count * INDEX_ENTRY.size
    if table_end > len(data):
        raise ValueError("Truncated index")
    entries = list(INDEX_ENTRY.iter_unpack(data[start:table_end]))
    for index, (offset, length) in enumerate(entries):
        if length and (offset < table_end or offset + length * unit_size > len(data)):
            raise ValueError(f"Index entry {index} points outside the payload")
    return entries


def write_display(source, target, encoding):
    data = source.read_bytes()
    version, prefix_count, display_count = struct.unpack_from("<IHH", data)
    start = 8 + prefix_count * INDEX_ENTRY.size
    entries = read_index(data, start, display_count, 1)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["display_index", "offset", "bytes", "text"])
        for index, (offset, length) in enumerate(entries):
            text = data[offset:offset + length].removesuffix(b"\x00").decode(encoding, errors="backslashreplace")
            writer.writerow([index, offset, length, text])
    return {"version": version, "prefix_entries": prefix_count, "display_entries": len(entries)}


def write_templates(source, target):
    data = source.read_bytes()
    count = struct.unpack_from("<H", data, 6)[0]
    entries = read_index(data, 8, count, TEMPLATE_FIELD.size)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["template_index", "field_index", "offset", "type", "word_1", "word_2", "word_3", "word_4"])
        for index, (offset, count) in enumerate(entries):
            fields = data[offset:offset + count * TEMPLATE_FIELD.size]
            for field_index, field in enumerate(TEMPLATE_FIELD.iter_unpack(fields)):
                writer.writerow([index, field_index, offset + field_index * TEMPLATE_FIELD.size, *field])
    return len(entries)


def read_language(source):
    data = source.read_bytes()
    locale, _, groups, first_offset = struct.unpack_from("<4I", data)
    start = 12 + groups * 4
    if not groups or not start <= first_offset <= len(data):
        raise ValueError("Invalid vtfb.v group index")
    label = data[start:first_offset].decode("utf-16-le").split("\x00", 1)[0]
    return {"locale_id": locale, "language_label": label, "groups": groups}


def write_audio(output, stem, raw, formats, alaw_table):
    pcm = decode_mulaw(raw)
    if "wav" in formats:
        with wave.open(str(output / f"{stem}.wav"), "wb") as wav:
            wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
            wav.writeframes(pcm)
    if "ulaw" in formats:
        (output / f"{stem}.ulaw").write_bytes(raw)
    if "alaw" in formats:
        (output / f"{stem}.alaw").write_bytes(raw.translate(alaw_table))
    return hashlib.sha256(pcm).hexdigest()


def extract(source, output, formats, encoding):
    bank = source / "phrase_s"
    if output.exists() or output.is_symlink():
        raise ValueError(f"{output} already exists. Choose a fresh output directory.")
    alaw_table = alaw_conversion_table() if "alaw" in formats else None
    size = bank.stat().st_size
    output.parent.mkdir(parents=True, exist_ok=True)

    with bank.open("rb") as stream, tempfile.TemporaryDirectory(prefix=".bcm4-", dir=output.parent) as temp_dir:
        index = read_phrase_index(stream, size)
        staged = Path(temp_dir) / "prompts"
        staged.mkdir()
        audio = staged / "audio"
        if formats:
            audio.mkdir()
        stream.seek(0)
        summary = {
            "source_bank_sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
            "source_directory_name": source.name,
            "audio_codec": "G.711 mu-law",
            "sample_rate": SAMPLE_RATE,
            "slots": len(index),
            "populated": sum(length > 0 for _, length, _ in index),
            "formats": list(formats),
        }
        language = source / "vtfb.v"
        if language.is_file():
            summary.update(read_language(language))
        templates = source / "template"
        if templates.is_file():
            summary["templates"] = write_templates(templates, staged / "templates.csv")
        display = source / "txtprmpt"
        if display.is_file():
            summary["text_encoding"] = encoding
            summary["display"] = write_display(display, staged / "display.csv", encoding)

        with (staged / "phrases.csv").open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["phrase_index", "offset", "bytes", "seconds", "ulaw_sha256", "pcm_sha256", "status"])
            for slot, (offset, length, _) in enumerate(index):
                if not length:
                    writer.writerow([slot, offset, 0, "0.000000", "", "", "empty"])
                    continue
                stream.seek(offset)
                raw = stream.read(length)
                if len(raw) != length or (length >= 4 and raw[:4] != b"\xff" * 4):
                    raise ValueError(f"Truncated or unsupported G.711 payload at phrase index {slot}")
                pcm_hash = write_audio(audio, f"phrase_{slot:04d}", raw, formats, alaw_table) if formats else ""
                writer.writerow([slot, offset, length, f"{length / SAMPLE_RATE:.6f}",
                                 hashlib.sha256(raw).hexdigest(), pcm_hash, "exported" if formats else "indexed"])
        (staged / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        staged.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language_directory", type=Path)
    parser.add_argument("output", type=Path, help="New output directory")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--format", choices=FORMATS, action="append", help="Repeat to select formats (default: all three)")
    modes.add_argument("--index-only", action="store_true", help="Export metadata without writing audio")
    parser.add_argument("--text-encoding", default="latin-1", help="Encoding of the display strings (default: latin-1)")
    args = parser.parse_args()
    formats = () if args.index_only else tuple(dict.fromkeys(args.format or FORMATS))
    try:
        codecs.lookup(args.text_encoding)
        summary = extract(args.language_directory, args.output, formats, args.text_encoding)
    except (OSError, ValueError, LookupError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"{summary['populated']} populated slots out of {summary['slots']} in {args.output}")


if __name__ == "__main__":
    main()
