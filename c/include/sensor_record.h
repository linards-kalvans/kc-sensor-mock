#ifndef SENSOR_RECORD_H
#define SENSOR_RECORD_H

#include <stdint.h>

#define SENSOR_VALUES_COUNT 296
#define SENSOR_RECORD_SIZE 632

#define MEASUREMENT_TYPE_SPECTRA 1
#define MEASUREMENT_TYPE_BACKGROUND_SPECTRA 2

struct sensor_record {
    uint16_t device_id;
    uint16_t measurement_type;
    uint32_t sequence_number;
    uint32_t dropped_records_total;
    uint64_t sensor_timestamp_us;
    uint64_t gps_timestamp_us;
    int32_t gps_latitude_e7;
    int32_t gps_longitude_e7;
    int32_t gps_altitude_mm;
    uint16_t values[SENSOR_VALUES_COUNT];
};

#endif /* SENSOR_RECORD_H */
