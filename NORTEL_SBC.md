# Nortel CallPilot SBC codec

The portable C11 codec encodes and decodes the 18 kbit/s sub-band stream used by the CallPilot 5.0 language CD. It uses fixed-point arithmetic and accepts signed 16-bit mono PCM at 8 kHz. Use the Python CLI for individual files, or select the library backend in the CD extractor. The C source, Python binding and codec verification tools use the [MIT license](LICENSE-SBC.txt).

## Build

In an MSYS2 MINGW64 terminal on Windows, build for a 64-bit Python.

~~~sh
mkdir -p build
gcc -std=c11 -O2 -shared nortel_sbc.c -o build/nortel_sbc.dll
~~~

On Linux, build the shared library with the system C compiler.

~~~sh
mkdir -p build
cc -std=c11 -O2 -fPIC -shared nortel_sbc.c -o build/libnortel_sbc.so
~~~

On macOS, use `cc -std=c11 -O2 -dynamiclib nortel_sbc.c -o build/libnortel_sbc.dylib`. Use the filename for your platform in the commands below. Python 3.11 or newer provides all the required modules.

## Convert a file or extract a CD

~~~sh
python nortel_sbc.py decode numbered-prompt prompt.wav --library build/nortel_sbc.dll
python nortel_sbc.py encode input-8k.wav prompt.sbc --library build/nortel_sbc.dll
python extract_callpilot5.py "CallPilot 5.0 CD Language Image.zip" build/callpilot5-en-ca --sbc-library build/nortel_sbc.dll
~~~

The encoder requires at least 240 input samples. Decoding returns a whole number of 256-sample frames, so a short final frame includes the codec's tail. The default stream uses the logical block lengths found on the CD. Use `--padded-blocks` for a file containing the DLL's fixed 8,192-byte buffer slots. This codec handles the documented 18 kbit/s raw stream. VBK packaging and other CallPilot codec modes need their own readers.

## Bitstream and filter arithmetic

| Item | Behavior |
| --- | --- |
| Storage block | Six-byte header, one or more frame groups, four-byte trailer marker, and 66 zero bytes. Each block is at most 8,176 bytes before transport padding. |
| Frame group | Two-byte big-endian length. After swapping adjacent payload bytes, the group exposes two or four 36-byte half-frames. |
| Frame symbols | Each half carries 12 active bands in a fixed order. Each band has a 4-bit scale and eight 2- or 4-bit signed-magnitude codes. |
| Encode | Prime the four-stage filter bank with 240 PCM samples, quantize the bands, and group up to 108 frames in each block. The analysis filter history continues across blocks produced in the same call. |
| Decode | Expand the band codes, reconstruct audio with four polyphase stages, and compensate the 225-sample synthesis delay. Each logical block starts with zeroed synthesis history, matching the factory prompt extraction path. |

The loader and wire layout are described in the [language CD format notes](CALLPILOT5_FORMAT.md#stored-blocks). Analysis and synthesis use explicit signed rounding and clipping. The DLL served as the compatibility oracle and is needed only to repeat those comparisons.

## Verify against the factory DLL

The archived DLL has SHA-256 `c48eb80a73a91b268f78cafe8baffe0b8298ed28141a52fa71887058496be56d`. The PCM decoder entry is at RVA `0xDF20`; the PCM-to-SBC entry is at `0xDFF0`. Each encoder comparison uses the same input PCM on both implementations. SBC is lossy, so comparison with the original speech uses a shared decoding oracle.

- Decoding matched the factory PCM for 144,986 logical blocks across 34 locale banks, covering 86,706 playable prompts. The Canadian English extractor also produced a byte-identical prompt CSV with the portable backend.
- The factory and portable encoders returned identical logical SBC bytes and identical padded buffers on 62 deterministic inputs from 240 to 32,768 samples. The vectors cover silence, impulses, tones, full-scale alternation, noise, and the boundary from one block to two.
- The test suite includes exact factory SBC and PCM hashes for six synthetic fixtures. Set `CALLPILOT_SBC_LIBRARY` to a compiled library and run `python -m unittest discover -s tests -v`.

To compare directly to the DLL, build the C library in the MSYS2 MINGW32 terminal and run the comparison with 32-bit Windows Python. Supply the language ZIP to check the archived prompts as well as the encoder vectors. Use repeated `--locale` options to restrict the prompt comparison to specific banks.

~~~sh
mkdir -p build
gcc -std=c11 -O2 -shared nortel_sbc.c -o build/nortel_sbc_x86.dll
py -3.13-32 verify_sbc_oracle.py "CallPilot 5.0 CD Language Image.zip" --codec NMCODEC.DLL --library build/nortel_sbc_x86.dll
~~~
