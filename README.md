# CallPilotPrompts

Research and conversion of factory prompts from Nortel CallPilot and Norstar Voice Mail / NAM. The companion [Asterisk prompt checklist](https://github.com/andrew867/JoanKenley-asterisk/blob/main/prompts.csv) identifies the phrases that would be most useful to recover.

## First sample

The inventory script uses Python 3.11 or newer.

- Record the product name, release, platform and language. Keep the original prompt filenames, directory structure and any nearby indexes or manifests.
- Start with a factory prompt directory and a few clips with known wording. A short digit, a voicemail menu prompt and a longer greeting give useful comparisons. Keep production mailbox data and customer recordings outside the sample.
- Keep the source files byte-for-byte. Use the inventory to record relative names, sizes, SHA-256 digests and the first 32 bytes before trying a decode.

```sh
python inventory.py intake/callpilot > callpilot-inventory.json
```

`intake/` and `build/` are local working directories. Keep generated inventories with the corresponding samples.

## Format and outputs

The first vendor samples are pending. The Dialogic ADPCM family is a candidate. Identify any container, sample rate, block boundaries, nibble order and restart state from the bytes and compare the results with known prompt playback before committing to a decoder. Keep CallPilot server and NAM formats distinct if samples show differences.

Keep the verified PCM WAV at its decoded sample rate. Produce 8 kHz mono `.ulaw` and `.alaw` derivatives for telephony playback. Record each output's source digest, the decoder version and settings, and keep the factory language and prompt identifier with the transcription. A WAV made from a compressed prompt is a decoded copy of that prompt.

[CallPilot 4.0 Administrator's Guide](https://www.tandemdata.com/Manuals/Nortel/Call%20Pilot/CP%204.0%20Administrator%27s%20Guide.pdf) documents customization and WAV import. Its import interface leaves the factory prompt storage format open.
