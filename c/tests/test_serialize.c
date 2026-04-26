#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "sensor_record.h"
#include "serialize.h"

int main(void) {
    struct sensor_record record = {0};
    uint8_t out[SENSOR_RECORD_SIZE];
    memset(out, 0, SENSOR_RECORD_SIZE);

    /* Populate with known values matching the golden fixture */
    record.device_id = 0x1234;
    record.measurement_type = MEASUREMENT_TYPE_BACKGROUND_SPECTRA;
    record.sequence_number = 0x01020304;
    record.dropped_records_total = 0x05060708;
    record.sensor_timestamp_us = 0x0102030405060708ULL;
    record.gps_timestamp_us = 0x1112131415161718ULL;
    record.gps_latitude_e7 = -123456789;
    record.gps_longitude_e7 = 0x0A0B0C0D;
    record.gps_altitude_mm = -1000;
    record.values[0] = 0x0102;
    record.values[1] = 0x0304;
    record.values[2] = 0x0605;
    record.values[3] = 0x0807;

    /* Test: null pointer rejection */
    assert(serialize_record(NULL, out, NULL, 0) == 1);

    /* Test: null output buffer rejection */
    assert(serialize_record(&record, NULL, NULL, 0) == 1);

    /* Test: invalid measurement_type rejection */
    record.measurement_type = 99;
    assert(serialize_record(&record, out, NULL, 0) == 1);

    /* Test: valid record serializes successfully */
    record.measurement_type = MEASUREMENT_TYPE_BACKGROUND_SPECTRA;
    memset(out, 0, SENSOR_RECORD_SIZE);
    assert(serialize_record(&record, out, NULL, 0) == 0);

    /* Verify little-endian layout: device_id at offset 0 */
    assert(out[0] == 0x34);
    assert(out[1] == 0x12);

    /* measurement_type at offset 2 */
    assert(out[2] == 0x02);
    assert(out[3] == 0x00);

    /* sequence_number at offset 4 (LE) */
    assert(out[4] == 0x04);
    assert(out[5] == 0x03);
    assert(out[6] == 0x02);
    assert(out[7] == 0x01);

    /* dropped_records_total at offset 8 (LE) */
    assert(out[8] == 0x08);
    assert(out[9] == 0x07);
    assert(out[10] == 0x06);
    assert(out[11] == 0x05);

    /* sensor_timestamp_us at offset 12 (LE) */
    assert(out[12] == 0x08);
    assert(out[13] == 0x07);
    assert(out[14] == 0x06);
    assert(out[15] == 0x05);
    assert(out[16] == 0x04);
    assert(out[17] == 0x03);
    assert(out[18] == 0x02);
    assert(out[19] == 0x01);

    /* gps_timestamp_us at offset 20 (LE) */
    assert(out[20] == 0x18);
    assert(out[21] == 0x17);
    assert(out[22] == 0x16);
    assert(out[23] == 0x15);
    assert(out[24] == 0x14);
    assert(out[25] == 0x13);
    assert(out[26] == 0x12);
    assert(out[27] == 0x11);

    /* gps_latitude_e7 at offset 28 (int32, LE, -123456789) */
    assert(out[28] == 0xeb);
    assert(out[29] == 0x32);
    assert(out[30] == 0xa4);
    assert(out[31] == 0xf8);

    /* gps_longitude_e7 at offset 32 (LE) */
    assert(out[32] == 0x0d);
    assert(out[33] == 0x0c);
    assert(out[34] == 0x0b);
    assert(out[35] == 0x0a);

    /* gps_altitude_mm at offset 36 (int32, LE, -1000) */
    assert(out[36] == 0x18);
    assert(out[37] == 0xfc);
    assert(out[38] == 0xff);
    assert(out[39] == 0xff);

    /* values[0] at offset 40 (LE) */
    assert(out[40] == 0x02);
    assert(out[41] == 0x01);

    /* values[3] at offset 46 (LE) */
    assert(out[46] == 0x07);
    assert(out[47] == 0x08);

    /* All remaining values should be zero */
    for (int i = 4; i < SENSOR_VALUES_COUNT; i++) {
        uint16_t v = (uint16_t)out[40 + i * 2] | ((uint16_t)out[40 + i * 2 + 1] << 8);
        assert(v == 0);
    }

    return 0;
}
