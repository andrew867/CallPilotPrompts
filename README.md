# CallPilotPrompts

**[v0.2.0](https://github.com/andrew867/CallPilotPrompts/releases/tag/v0.2.0)** · [Changelog](CHANGELOG.md)

Tools to extract factory prompts from the Nortel CallPilot 5.0 language CDs and BCM 4.0. The repository includes a portable encoder and decoder for CallPilot's 18 kbit/s SBC, plus extractors for BCM speech banks and IVR MMF V3 files.

## Extract CallPilot 5.0 audio

Build the [portable C11 library](NORTEL_SBC.md#build), then pass it to the extractor. This example uses the Windows library and the Canadian English locale.

~~~powershell
python extract_callpilot5.py "CallPilot 5.0 CD Language Image.zip" build/callpilot5-en-ca --sbc-library build/nortel_sbc.dll
~~~

The portable decoder matched the factory decoder on 144,986 logical blocks across 34 locale banks. The command above exports 2,735 Canadian English WAVs and a prompt index. Use `--locale 1033` for US English. The SBC CLI also encodes 8 kHz mono PCM WAVs and decodes individual SBC files. [Codec build and usage](NORTEL_SBC.md) · [Language CD layout](CALLPILOT5_FORMAT.md)

## Extract BCM 4.0 audio

Use Python 3.11 or newer. Install FFmpeg on `PATH` for A-law output.

```powershell
python inventory.py intake/bcm4 > build/bcm4-intake-inventory.json
python extract_bcm4.py intake/bcm4/part6/nn/CallPilot/prmptupd/lang_0 build/bcm4-en-us
python extract_mmf.py intake/bcm4/part6/nn/ivr/mmf/numset.mmi build/bcm4-mmf/numset
```

Create the `build` folder before redirecting the inventory. Use a new output directory for each extraction. Both extractors default to 8 kHz mono PCM WAV, raw μ-law and raw A-law. To omit A-law, pass `--format wav --format ulaw`. `--index-only` writes indexes and manifests without audio.

- `extract_bcm4.py` reads `phrase_s` and the companion files if present. Its output includes `phrases.csv`, `manifest.json`, `templates.csv`, and `display.csv`. `lang_0` is labeled American English. Its μ-law exports preserve the stored clip bytes.
- `extract_mmf.py` reads the adjacent `.mmi` and `.mmd` files. The output includes `elements.csv` with the named element IDs, source page offsets, and hashes. Unconverted codec payloads are written as original `.bin` slices.

The [BCM 4.0 format notes](BCM4_FORMAT.md) document the indexes, audio byte layout, native-library checks, and open questions.

## Asterisk candidates

[asterisk-candidates.csv](asterisk-candidates.csv) proposes matches against gaps in the [JoanKenley-asterisk prompt checklist](https://github.com/andrew867/JoanKenley-asterisk/blob/main/prompts.csv). `audio_path` is relative to the `build` directory created by the commands above. Labels and spot transcriptions identify likely wording. Listen for the intended wording, pronunciation, level, and speaker before moving clips into the pack. The DMS mappings take priority in the companion project.

## Intake

Keep each release and platform in its own intake directory. Preserve original filenames, prompt indexes and paths, and record file hashes using `inventory.py`. Use factory files without mailbox or customer recordings. The vendor files and generated audio belong in the local `intake/` and `build/` directories.

## License

The portable SBC code and its verification tools are MIT-licensed, copyright © 2026 Andrew Green. [License text](LICENSE-SBC.txt)
