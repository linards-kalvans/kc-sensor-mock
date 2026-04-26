#include "serialize.h"

#include <string.h>

static void write_u16_le(uint8_t *out, uint16_t value) {
    out[0] = (uint8_t)(value & 0xFF);
    out[1] = (uint8_t)((value >> 8) & 0xFF);
}

static void write_u32_le(uint8_t *out, uint32_t value) {
    out[0] = (uint8_t)(value & 0xFF);
    out[1] = (uint8_t)((value >> 8) & 0xFF);
    out[2] = (uint8_t)((value >> 16) & 0xFF);
    out[3] = (uint8_t)((value >> 24) & 0xFF);
}

static void write_u64_le(uint8_t *out, uint64_t value) {
    out[0] = (uint8_t)(value & 0xFF);
    out[1] = (uint8_t)((value >> 8) & 0xFF);
    out[2] = (uint8_t)((value >> 16) & 0xFF);
    out[3] = (uint8_t)((value >> 24) & 0xFF);
    out[4] = (uint8_t)((value >> 32) & 0xFF);
    out[5] = (uint8_t)((value >> 40) & 0xFF);
    out[6] = (uint8_t)((value >> 48) & 0xFF);
    out[7] = (uint8_t)((value >> 56) & 0xFF);
}

static void write_i32_le(uint8_t *out, int32_t value) {
    /* Cast to uint32_t to get two's-complement bit pattern, then write LE */
    write_u32_le(out, (uint32_t)value);
}

int serialize_record(const struct sensor_record *record,
                     uint8_t out[SENSOR_RECORD_SIZE],
                     char *error_buf,
                     size_t error_buf_size) {
    (void)error_buf;
    (void)error_buf_size;

    if (record == NULL || out == NULL) {
        return 1;
    }

    if (record->measurement_type != MEASUREMENT_TYPE_SPECTRA &&
        record->measurement_type != MEASUREMENT_TYPE_BACKGROUND_SPECTRA) {
        return 1;
    }

    /* Clear output buffer */
    memset(out, 0, SENSOR_RECORD_SIZE);

    /* Metadata fields at offsets 0..39 */
    write_u16_le(out + 0,  record->device_id);
    write_u16_le(out + 2,  record->measurement_type);
    write_u32_le(out + 4,  record->sequence_number);
    write_u32_le(out + 8,  record->dropped_records_total);
    write_u64_le(out + 12, record->sensor_timestamp_us);
    write_u64_le(out + 20, record->gps_timestamp_us);
    write_i32_le(out + 28, record->gps_latitude_e7);
    write_i32_le(out + 32, record->gps_longitude_e7);
    write_i32_le(out + 36, record->gps_altitude_mm);

    /* 296 uint16 values starting at byte offset 40 */
    for (int i = 0; i < SENSOR_VALUES_COUNT; i++) {
        write_u16_le(out + 40 + i * 2, record->values[i]);
    }

    return 0;
}
