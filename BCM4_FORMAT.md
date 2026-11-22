# BCM 4.0 prompt format

The inspected BCM 4.0 Linux image identifies itself as build `2.03a`, August 28, 2006. CallPilot's `voicemail` and the IVR's `mmf2vfs` executable are little-endian 32-bit x86 ELF. CallPilot's voice files use little-endian indexes. The IVR MMF files use big-endian indexes independently of the host architecture. For numbered SBC prompts from the CallPilot 5.0 language CDs, see the [language CD guide](CALLPILOT5_FORMAT.md).

## CallPilot language directories

The factory update tree is `nn/CallPilot/prmptupd/lang_*`. The Hebrew voice bank is in `prmptheb/lang_249`. The separate `prmptupd/lang_249` has a display table only.

| File | Purpose | Verified sample |
| --- | --- | --- |
| `phrase_s` | Indexed bank of single speech clips | `lang_0` has 1,072 slots, including 1,070 nonempty |
| `template` | Indexed lists of fields used to compose voice prompts | 731 templates in `lang_0` |
| `txtprmpt` | Catalog of display strings | 87 prefix entries and 3,180 display slots in `lang_0` |
| `vtfb.v` | Locale ID, group offsets, language name and original build-path string | `0x0409`, `English(American)` in `lang_0` |

### Speech bank from byte 0

| File offset | Bytes | Meaning |
| --- | ---: | --- |
| `0x00` | 4 | Number of phrase slots, little-endian unsigned |
| `0x04` | 20 | Five zero words in the observed banks |
| `0x18` | `12 × slots` | Slot rows. Each is three little-endian 32-bit words: absolute payload offset, payload bytes and a zero word |
| `0x18 + 12 × slots` | Through EOF | Concatenated G.711 μ-law audio at 8,000 samples/s, mono, one byte per sample |

The first `lang_0` audio starts at `0x3258`. Slot 0 has 14,310 bytes and spot transcription yields “To continue, press 2.” Slot 1 starts at byte 27,198. Empty slots retain an index row with length zero. All 25 banks in the sample have contiguous offsets and a last entry ending at EOF. The extractor exported the American English bank and validated the indexes and payload framing of all 25 banks, totaling 27,599 nonempty slots. Speech and language identifications are spot checks.

`phrase_s` bytes are already in standard μ-law code order. `0xff` at the head of the clips represents digital silence. The `.ulaw` output for each slot is a direct byte copy, its WAV expands each code to 16-bit PCM, and its `.alaw` transcodes the same waveform.

`libnvm.so` contains separate G.711 and OKI ADPCM paths. That confirms the software handles both families. The layout, silence codes and intelligible decode identify this particular factory speech bank as μ-law.

### Indexes alongside the audio

- `template` has a 16-bit count at `0x06`. Its table starts at `0x08`, with six bytes per entry: a 32-bit absolute offset and a 16-bit field count. Each field is five 16-bit words. `PXReadVPTemplateIndex` and `PXReadVPTemplateField` in `libnvm.so` corroborate those row sizes. The CSV exposes the field type and four remaining words. Resolving speech IDs and runtime substitutions needs further work.
- `txtprmpt` starts with a 32-bit version followed by two 16-bit counts, for prefix and display entries. The prefix entries use six bytes apiece. The display rows start at `0x08 + 6 × prefix_count` and contain a 32-bit absolute offset and 16-bit byte length. `lang_0` display row 0 is “First Prompt - Do Not Use.” Speech slot 0 says “To continue, press 2.” The CSV uses Latin-1 to preserve individual display bytes by default. Supply the relevant encoding with `--text-encoding` for a localized bank.
- `vtfb.v` starts with a 32-bit locale ID and has a 32-bit group count at `0x08`. The group offsets start at `0x0c`. The gap between that index and the first group contains the UTF-16LE language label and build path. `lang_253` and `lang_255` both report `English(American)`, while their build paths are associated with Cantonese and China. Keep the directory ID and source digest when identifying their audio.

## Separate IVR MMF V3 pairs

The IVR under `nn/ivr/mmf` ships `beep`, `dtmf`, `mf`, `numdemo`, `numset`, `tdd` and `uscpd` as paired `.mmi` indexes and `.mmd` page files. The executable-side tools and libraries are in `opt/vps`.

| File and offset | Meaning |
| --- | --- |
| `.mmi + 0x00` | Magic `11 22 33 44`, followed in the header by `MMF V3 18-nov-96` |
| `.mmi + 0x34` | Element attribute packet (EAP) stride, `0x400` |
| `.mmi + 0x3c` | EAP table offset, `0x2000`. Skip slot 0 |
| `.mmd + 0x00` | Magic `55 66 77 88` |
| `.mmd + 0x40` | Data page size, `0x2000` |

The meaningful EAP offsets observed in these pairs are:

| Relative offset | Meaning |
| --- | --- |
| `0x00`, `0x04` | Element ID and kind. Kind `0x30` carries audio. A zero kind marks an unused slot |
| `0x20`, `0x24` | Format marker and codec ID |
| `0x28`, `0x30` | Name length in bytes and start of the name |
| `0x2c` | Audio payload length in bytes |
| `0xd8` | Array of absolute `.mmd` page offsets, in playback order |

Read the indexed pages and keep exactly the declared payload length. For marker `0x10004` and codec ID 4, XOR every byte with `0xff` to recover standard μ-law. `libmmf2vfs.so` function `generate_phrase_file` passes that mask to `libconv.so:maskData` for codec 4. Spot-checking DTMF 1 and 2 at 8 kHz gives approximately 697/1209 and 697/1336 Hz.

The supplied pairs contain 778 codec-4 elements, of which 642 belong to `numset`. The other 39 audio elements are marker `0x10002`, codec ID 3. These are exported as original `.bin` slices and labeled `unconverted_codec`. Among them, 15 DTMF elements contain only repeated `0x01` bytes, so the apparent duplicate labels do not establish an alternate recording. The precise handling of codec ID 3 remains open.

`numset` holds cardinal and ordinal numbers, weekdays, months, letters and other short vocabulary. Its descriptive element credits Nortel Audio Services without naming the speaker. The factory American English CallPilot voice and `numset` should each be compared with known Joan Kenley recordings before attributing either bank to her.

## Scope

These offsets describe the inspected BCM 4.0 image. A Meridian 1 CallPilot 201i or a Norstar NAM sample needs its own checks of container layout, codec and prompt IDs.
