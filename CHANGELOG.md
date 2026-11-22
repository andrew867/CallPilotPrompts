# CallPilotPrompts changelog

## v0.2.0

- Added a portable C11 encoder and decoder for Nortel's 18 kbit/s CallPilot SBC. The Python CLI converts between SBC and 8 kHz mono PCM WAV and supports both logical blocks and fixed 8,192-byte buffer slots.
- Added the portable library backend to the CallPilot 5.0 CD extractor. The factory DLL backend remains available for reference comparisons.
- Matched the factory decoder's PCM on 144,986 logical blocks across 34 locale banks. The encoder matched the factory bytes for 62 deterministic inputs, including the padded output buffers.
- Added build instructions, fixed-point codec notes, and tests against factory outputs. The SBC MIT license names Andrew Green.

Start with the [codec guide](NORTEL_SBC.md) or the [CallPilot 5.0 extraction guide](CALLPILOT5_FORMAT.md). The codec handles the raw 18 kbit/s prompt stream. VBK containers and other CallPilot codec modes require separate readers.

## v0.1.0-alpha.1

- Added extractors for BCM 4.0 speech banks and IVR MMF files. MMF codec 3 payloads were preserved as original bytes for analysis.
- Added CallPilot 5.0 language CD extraction using the 32-bit Nortel Desktop Messaging DLL. The Canadian and US English banks each produced 2,735 WAVs.
- Added format notes and a BCM-to-Asterisk prompt candidate list.
