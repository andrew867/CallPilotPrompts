/* SPDX-License-Identifier: MIT */
#ifndef NORTEL_SBC_H
#define NORTEL_SBC_H

#include <stddef.h>
#include <stdint.h>

/* Decode one logical 18 kbit/s CallPilot block. Return PCM frames, or -1
   for an invalid block or insufficient output space. */
int nortel_sbc_decode_block(const uint8_t *block, size_t size,
                            int16_t *pcm, size_t capacity);

/* Encode signed 8 kHz mono PCM to logical blocks. Inputs under 240 samples
   and insufficient capacities return zero. */
size_t nortel_sbc_encoded_size(size_t samples);
size_t nortel_sbc_encode(const int16_t *pcm, size_t samples,
                         uint8_t *output, size_t capacity);

#endif
