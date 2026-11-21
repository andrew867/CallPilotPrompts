# CallPilot 5.0 language CD prompts

The examined two-disc language image identifies itself as build `05.00.44.00`. Its prompt export log identifies the application release as `Master 02`. The ZIP's SHA-256 is `eae4b2f84e2851e2a456cfa2cb8769f6bdc398eba0367a20c5012ce6da122935`.

## Find the prompts

| Path under a language directory | Contents |
| --- | --- |
| `prompt/voice/<id>` | Numbered Nortel SBC speech files. The filenames have no extension. |
| `prompt/data/langinfo.lng` | Locale, language and release metadata |
| `prompt/data/ExportLog.txt` | Templates, fixed segment IDs and original recording names |
| `prompt/data/vtfa.v` and `vtfb.v` | Text and binary variable translation tables, including weekdays and ordinals |
| `prompt/data/sceapp0.l` and `sceapp0.m` | Packed prompt templates and their indexes |

Disc 1 has Canadian English `lang4105` and American English `lang1033`. Each has 2,736 numeric voice files. Seven IDs differ across these locales. Each bank includes a zero-byte file. The Canadian export contains 2,735 playable WAVs. The legacy Desktop Messaging converter expands them at 8 kHz, mono, to signed 16-bit PCM. In the spot checks, `4504` says “zero,” `3905` says “star,” and `101` offers mailbox login or the attendant.

## Stored blocks

Each numbered speech file is a sequence of blocks. A little-endian 16-bit block size at offset 0 includes the size field itself. The next block starts at that offset plus the size. Full intervening blocks in this release are 8,176 bytes. The first logical block of Canadian `101` is 8,176 bytes and the second is 3,676 bytes. Padding in the tail belongs to the stored block. The decoder zero-pads each logical block to the 8,192-byte working buffer used by the native library.

In the tested layout, bytes 2 through 6 are zero, the first frame group begins with `96` or `4E` hex, and the block ends in at least 66 zero bytes. Frames are 256 output samples each. A block yields `floor((size - 76) / 75)` frames of that size. This relationship is verified against the native decoder on every exported block. This description covers the archived prompt layout. Desktop message VBK containers and BCM 4.0 `phrase_s` have separate layouts.

Nortel describes its SBC for messaging as proprietary sub-band coding at 18 kbit/s. The numbered prompt files here use that decoder. [Nortel CallPilot Planning and Engineering Guide](https://www.tandemdata.com/Manuals/Nortel/Call%20Pilot/CP%204.0%20Planning%20and%20Engineering%20Guide.pdf)

## Reproduce the extraction

Use a 32-bit Windows Python. `extract_callpilot5.py` calls the SBC decoder in the specific 32-bit `NMCODEC.DLL` from the BCM 4.0 Desktop Messaging client. The script verifies the DLL by SHA-256 since its internal entry point at RVA `0xDF20` is specific to that build. It neither installs nor registers the client.

In the extracted BCM 4.0 Linux system image, the installer is `srv/www/apps/public/CallPilotDesktopMessaging.exe`. Windows `tar.exe` can extract the nested client in an empty local directory.

~~~powershell
tar -xf CallPilotDesktopMessaging.exe /web/audio_enu.exe
tar -xf web/audio_enu.exe NMCODEC.DLL
py -3.13-32 extract_callpilot5.py "CallPilot 5.0 CD Language Image.zip" build/callpilot5-en-ca --codec NMCODEC.DLL
~~~

Add `--locale 1033` and choose a new output directory for American English. The CSV records the source and PCM hashes, original and installed prompt IDs, and output frame counts. Vendor media, the DLL and the generated WAVs are kept local. [Asterisk pack builder](https://github.com/andrew867/JoanKenley-asterisk)
