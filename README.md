# CallPilotPrompts

Factory-prompt format research and extraction for Nortel CallPilot and Norstar Voice Mail / NAM. This repository covers the BCM 4.0 Linux CallPilot speech banks and the separate IVR MMF V3 banks in the same image.

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
