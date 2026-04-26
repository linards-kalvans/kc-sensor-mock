#ifndef SERIALIZE_H
#define SERIALIZE_H

#include <stddef.h>
#include <stdint.h>

#include "sensor_record.h"

int serialize_record(const struct sensor_record *record,
                     uint8_t out[SENSOR_RECORD_SIZE],
                     char *error_buf,
                     size_t error_buf_size);

#endif /* SERIALIZE_H */
