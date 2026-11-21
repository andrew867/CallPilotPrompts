# CallPilotPrompts 0.1.0 alpha 1

First tagged release of the format notes and prompt extractors for Nortel BCM 4.0 and CallPilot 5.0.

- Decode BCM 4.0 speech banks, preserve companion template indexes, and extract named clips from the separate IVR MMF files.
- Extract CallPilot 5.0 Canadian and American English language-disc prompts. Each tested locale produced 2,735 WAVs. The export includes source hashes, voice IDs and sample counts.
- Use the BCM-to-Asterisk candidate list when matching prompts to Asterisk sound IDs.

## Try it

Download **Source code (zip)** and follow the guide for the media you have. The CallPilot 5.0 decoder requires the documented build of Nortel's 32-bit `NMCODEC.DLL` and 32-bit Windows Python. The BCM tools run with Python 3.11 or newer.

The release includes tools, format notes and mappings. Supply your own vendor media and codec DLL. MMF codec 3 payloads are preserved for analysis. Voice attribution remains open.

[BCM 4.0 guide](BCM4_FORMAT.md) · [CallPilot 5.0 guide](CALLPILOT5_FORMAT.md)
