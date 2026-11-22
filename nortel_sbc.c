/* SPDX-License-Identifier: MIT */
#include "nortel_sbc.h"

#include <string.h>

enum {
    BLOCK_HEADER = 6,
    BLOCK_TAIL = 70,
    BLOCK_LIMIT = 8176,
    FRAME_BYTES = 72,
    FRAME_SAMPLES = 256,
    HALF_FRAME_BYTES = 36,
    FILTER_TAPS = 16,
    SYNTHESIS_DELAY = 225,
    ANALYSIS_PRIME = 240,
    FRAMES_PER_BLOCK = 108,
    FULL_GROUP = 150,
    SHORT_GROUP = 78
};

static const uint8_t block_tail[BLOCK_TAIL] = {0xad, 0xde, 0xef, 0xbe};
static const uint8_t wire_bands[] = {0, 4, 12, 2, 6, 14, 1, 5, 13, 3, 7, 15};
static const uint8_t widths[] = {2, 4, 4, 4, 2, 2, 2, 2, 0, 0, 0, 0, 2, 2, 2, 2};
static const uint8_t weights[] = {4, 2, 2, 2, 8, 4, 4, 4, 128, 64, 16, 32, 8, 16, 16, 16};
static const uint16_t scales[] = {
    32, 64, 128, 192, 320, 448, 704, 960, 1472, 1984, 3008, 4032, 6080, 8128, 12224, 16320
};

/* Polyphase interpolation taps in Q16, newest sample first. The other
   phase uses the same taps in reverse order. */
static const int16_t taps[FILTER_TAPS] = {
    148, -130, 56, 136, -522, 1276, -2918, 8714,
    30388, -6510, 3592, -2292, 1488, -932, 536, -260
};

typedef struct {
    int16_t forward[FILTER_TAPS];
    int16_t reverse[FILTER_TAPS];
} FilterPair;

typedef struct {
    FilterPair stages[4][8];
} FilterBank;

static int16_t clamp16(int32_t value)
{
    if (value > INT16_MAX)
        return INT16_MAX;
    if (value < INT16_MIN)
        return INT16_MIN;
    return (int16_t)value;
}

static int32_t floor_div(int32_t value, int32_t divisor)
{
    return value / divisor - (value % divisor < 0);
}

static int16_t wrap16(int32_t value)
{
    uint32_t low = (uint32_t)value & 0xffff;
    return (int16_t)(low < 0x8000 ? (int32_t)low : (int32_t)low - 0x10000);
}

static unsigned take_bits(const uint8_t *data, unsigned *position, unsigned width)
{
    /* The 2- and 4-bit fields are aligned within each byte. */
    unsigned shift = 8 - (*position % 8) - width;
    unsigned result = (data[*position / 8] >> shift) & ((1u << width) - 1);
    *position += width;
    return result;
}

static void expand_codes(const uint8_t frame[FRAME_BYTES], int16_t bands[FRAME_SAMPLES])
{
    unsigned position = 0;
    memset(bands, 0, FRAME_SAMPLES * sizeof(*bands));
    for (unsigned half = 0; half < 2; ++half) {
        for (unsigned i = 0; i < sizeof(wire_bands); ++i) {
            unsigned band = wire_bands[i];
            unsigned width = widths[band];
            /* A scale index applies to eight samples of one band. The
               low bit of each code is its sign. */
            int32_t step = scales[take_bits(frame, &position, 4)] >> width;
            for (unsigned sample = 0; sample < 8; ++sample) {
                unsigned code = take_bits(frame, &position, width);
                int32_t level = (code & 1) ? -(int32_t)code : (int32_t)(code | 1);
                bands[(8 * half + sample) * 16 + band] = (int16_t)floor_div(level * step, weights[band]);
            }
        }
    }
}

static void filter_pair(FilterPair *history, int16_t forward, int16_t reverse,
                        int16_t *filtered_forward, int16_t *filtered_reverse)
{
    int32_t forward_acc = 0, reverse_acc = 0;
    for (unsigned tap = FILTER_TAPS - 1; tap > 0; --tap) {
        history->forward[tap] = history->forward[tap - 1];
        history->reverse[tap] = history->reverse[tap - 1];
    }
    history->forward[0] = forward;
    history->reverse[0] = reverse;
    for (unsigned tap = 0; tap < FILTER_TAPS; ++tap) {
        forward_acc += taps[tap] * history->forward[tap];
        reverse_acc += taps[FILTER_TAPS - 1 - tap] * history->reverse[tap];
    }
    *filtered_forward = wrap16(floor_div(forward_acc, 65536));
    *filtered_reverse = wrap16(floor_div(reverse_acc, 65536));
}

static void interpolate(FilterPair *histories, unsigned width,
                        const int16_t input[FRAME_SAMPLES], int16_t output[FRAME_SAMPLES])
{
    for (unsigned i = 0; i < FRAME_SAMPLES; i += width) {
        for (unsigned j = 0; j < width / 2; ++j) {
            int32_t first = input[i + 2 * j];
            int32_t second = input[i + 2 * j + 1];
            filter_pair(&histories[j], clamp16(2 * (first - second)), clamp16(2 * (first + second)),
                        &output[i + j], &output[i + j + width / 2]);
        }
    }
}

static void synthesize(FilterBank *state, const int16_t bands[FRAME_SAMPLES],
                       int16_t samples[FRAME_SAMPLES])
{
    int16_t temporary[FRAME_SAMPLES];
    interpolate(state->stages[0], 16, bands, temporary);
    interpolate(state->stages[1], 8, temporary, samples);
    interpolate(state->stages[2], 4, samples, temporary);
    interpolate(state->stages[3], 2, temporary, samples);
}

static void append_samples(const int16_t samples[FRAME_SAMPLES], unsigned first,
                           unsigned end, int16_t **out)
{
    for (unsigned i = first; i < end; ++i)
        *(*out)++ = clamp16((int32_t)samples[i] * 2);
}

static int unpack_group(const uint8_t *data, size_t size, uint8_t frames[2 * FRAME_BYTES])
{
    uint8_t unpacked[FULL_GROUP - 2];
    size_t length = size - 2;
    unsigned halves = size == FULL_GROUP ? 4 : 2;
    size_t offset = 0;
    /* Swap byte pairs before reading the four half-frame lengths. */
    for (size_t i = 0; i < length; ++i)
        unpacked[i] = data[2 + (i ^ 1)];
    for (unsigned half = 0; half < 4; ++half) {
        if (half < halves) {
            if (unpacked[offset++] != HALF_FRAME_BYTES + 1)
                return -1;
            memcpy(frames + half * HALF_FRAME_BYTES, unpacked + offset, HALF_FRAME_BYTES);
            offset += HALF_FRAME_BYTES;
        } else if (unpacked[offset++] != 1) {
            return -1;
        }
    }
    return (int)halves / 2;
}

int nortel_sbc_decode_block(const uint8_t *block, size_t size,
                            int16_t *pcm, size_t capacity)
{
    FilterBank state = {0};
    int16_t bands[FRAME_SAMPLES], samples[FRAME_SAMPLES];
    size_t position = BLOCK_HEADER, sample_count = 0;
    int16_t *out = pcm;
    unsigned first = SYNTHESIS_DELAY;
    if (!block || !pcm || size < 154 || size > BLOCK_LIMIT ||
        (size_t)(block[0] | block[1] << 8) != size ||
        block[2] || block[3] || block[4] || block[5] ||
        memcmp(block + size - BLOCK_TAIL, block_tail, BLOCK_TAIL))
        return -1;
    size_t end = size - BLOCK_TAIL;
    while (position < end) {
        uint8_t frames[2 * FRAME_BYTES];
        if (end - position < 2)
            return -1;
        size_t length = (size_t)block[position] << 8 | block[position + 1];
        if ((length != FULL_GROUP && length != SHORT_GROUP) || length > end - position ||
            (length == SHORT_GROUP && length != end - position))
            return -1;
        int count = unpack_group(block + position, length, frames);
        if (count < 0 || (size_t)count * FRAME_SAMPLES > capacity - sample_count)
            return -1;
        for (int frame = 0; frame < count; ++frame) {
            expand_codes(frames + frame * FRAME_BYTES, bands);
            synthesize(&state, bands, samples);
            append_samples(samples, first, FRAME_SAMPLES, &out);
            first = 0;
        }
        sample_count += (size_t)count * FRAME_SAMPLES;
        position += length;
    }
    memset(bands, 0, sizeof(bands));
    /* Flush just enough output to compensate the initial filter delay. */
    synthesize(&state, bands, samples);
    append_samples(samples, 0, SYNTHESIS_DELAY, &out);
    return (int)sample_count;
}

static void decimate(FilterPair *histories, unsigned width, unsigned length,
                     const int16_t *input, int16_t *output)
{
    for (unsigned i = 0; i < length; i += 2 * width) {
        for (unsigned j = 0; j < width; ++j) {
            int16_t second, first;
            filter_pair(&histories[j], input[i + width + j], input[i + j],
                        &second, &first);
            output[i + 2 * j] = wrap16((int32_t)second + first);
            output[i + 2 * j + 1] = wrap16((int32_t)second - first);
        }
    }
}

static void analyze(FilterBank *state, const int16_t *pcm, unsigned length,
                    int16_t bands[FRAME_SAMPLES])
{
    int16_t temporary[FRAME_SAMPLES];
    decimate(state->stages[0], 1, length, pcm, temporary);
    decimate(state->stages[1], 2, length, temporary, bands);
    decimate(state->stages[2], 4, length, bands, temporary);
    decimate(state->stages[3], 8, length, temporary, bands);
}

static void put_bits(uint8_t *data, unsigned *position, unsigned width, unsigned value)
{
    unsigned shift = 8 - (*position % 8) - width;
    data[*position / 8] |= (uint8_t)(value << shift);
    *position += width;
}

static unsigned choose_scale(unsigned peak)
{
    unsigned biased = peak + 66;
    if (biased > INT16_MAX)
        biased = INT16_MAX;
    unsigned octave = 7;
    for (unsigned normalized = biased; normalized < 8192; normalized <<= 1)
        --octave;
    return (16 * octave + ((biased >> (octave + 2)) & 15)) >> 3;
}

static unsigned quantize(int32_t value, unsigned width, unsigned scale)
{
    unsigned amplitude = (unsigned)(value < 0 ? -value : value);
    if (amplitude > INT16_MAX)
        amplitude = INT16_MAX;
    unsigned code = value < 0;
    unsigned threshold = scale / 2;
    for (unsigned bit = 1u << (width - 1); bit > 1; bit >>= 1) {
        unsigned step = (scale * bit) >> width;
        if (amplitude > threshold) {
            code |= bit;
            threshold += step / 2;
        } else {
            threshold -= step / 2;
        }
    }
    return code;
}

static void quantize_frame(const int16_t bands[FRAME_SAMPLES], uint8_t frame[FRAME_BYTES])
{
    unsigned position = 0;
    memset(frame, 0, FRAME_BYTES);
    for (unsigned half = 0; half < 2; ++half) {
        for (unsigned i = 0; i < sizeof(wire_bands); ++i) {
            unsigned band = wire_bands[i], width = widths[band];
            int32_t levels[8];
            unsigned peak = 0;
            for (unsigned sample = 0; sample < 8; ++sample) {
                levels[sample] = (int32_t)bands[(half * 8 + sample) * 16 + band] * weights[band];
                unsigned amplitude = (unsigned)(levels[sample] < 0 ? -levels[sample] : levels[sample]);
                if (amplitude > peak)
                    peak = amplitude;
            }
            unsigned scale = choose_scale(peak);
            put_bits(frame, &position, 4, scale);
            for (unsigned sample = 0; sample < 8; ++sample)
                put_bits(frame, &position, width, quantize(levels[sample], width, scales[scale]));
        }
    }
}

static size_t logical_size(size_t frames)
{
    return BLOCK_HEADER + BLOCK_TAIL + (frames / 2) * FULL_GROUP + (frames % 2) * SHORT_GROUP;
}

size_t nortel_sbc_encoded_size(size_t samples)
{
    if (samples < ANALYSIS_PRIME)
        return 0;
    size_t frames = 1 + (samples - 1) / FRAME_SAMPLES;
    size_t remainder = frames % FRAMES_PER_BLOCK;
    return (frames / FRAMES_PER_BLOCK) * BLOCK_LIMIT + (remainder ? logical_size(remainder) : 0);
}

static void read_pcm(const int16_t **pcm, size_t *remaining, int16_t *input, unsigned length)
{
    unsigned count = *remaining < length ? (unsigned)*remaining : length;
    for (unsigned i = 0; i < count; ++i)
        input[i] = (int16_t)floor_div((*pcm)[i], 2);
    memset(input + count, 0, (length - count) * sizeof(*input));
    *pcm += count;
    *remaining -= count;
}

static void encode_group(FilterBank *state, const int16_t **pcm, size_t *remaining,
                         uint8_t *output, unsigned frames)
{
    int16_t input[FRAME_SAMPLES], bands[FRAME_SAMPLES];
    uint8_t stream[FULL_GROUP - 2];
    unsigned cursor = 0;
    for (unsigned f = 0; f < frames; ++f) {
        uint8_t compressed[FRAME_BYTES];
        read_pcm(pcm, remaining, input, FRAME_SAMPLES);
        analyze(state, input, FRAME_SAMPLES, bands);
        quantize_frame(bands, compressed);
        for (unsigned half = 0; half < 2; ++half) {
            stream[cursor++] = HALF_FRAME_BYTES + 1;
            memcpy(stream + cursor, compressed + half * HALF_FRAME_BYTES, HALF_FRAME_BYTES);
            cursor += HALF_FRAME_BYTES;
        }
    }
    if (frames == 1) {
        stream[cursor++] = 1;
        stream[cursor++] = 1;
    }
    output[0] = 0;
    output[1] = (uint8_t)(2 + cursor);
    for (unsigned i = 0; i < cursor; ++i)
        output[2 + i] = stream[i ^ 1];
}

size_t nortel_sbc_encode(const int16_t *pcm, size_t samples,
                         uint8_t *output, size_t capacity)
{
    size_t total = nortel_sbc_encoded_size(samples);
    if (!pcm || !output || !total || capacity < total)
        return 0;
    size_t frames = 1 + (samples - 1) / FRAME_SAMPLES;
    FilterBank state = {0};
    int16_t input[FRAME_SAMPLES], unused[FRAME_SAMPLES];
    read_pcm(&pcm, &samples, input, ANALYSIS_PRIME);
    /* Prime once per input stream. Subsequent logical blocks share the
       analysis history, as they do in one native encode call. */
    analyze(&state, input, ANALYSIS_PRIME, unused);
    while (frames) {
        unsigned block_frames = frames < FRAMES_PER_BLOCK ? (unsigned)frames : FRAMES_PER_BLOCK;
        size_t size = logical_size(block_frames);
        memset(output, 0, BLOCK_HEADER);
        output[0] = (uint8_t)size;
        output[1] = (uint8_t)(size >> 8);
        uint8_t *group = output + BLOCK_HEADER;
        for (unsigned f = 0; f < block_frames; f += 2) {
            unsigned count = block_frames - f >= 2 ? 2 : 1;
            encode_group(&state, &pcm, &samples, group, count);
            group += count == 2 ? FULL_GROUP : SHORT_GROUP;
        }
        memcpy(group, block_tail, BLOCK_TAIL);
        output += size;
        frames -= block_frames;
    }
    return total;
}
