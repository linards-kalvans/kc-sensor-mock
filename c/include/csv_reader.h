#ifndef CSV_READER_H
#define CSV_READER_H

#include <stddef.h>

#include "sensor_record.h"

/*
 * Read a CSV file of sensor records.
 *
 * Expects a header row matching the canonical schema exactly:
 *   device_id,measurement_type,sequence_number,dropped_records_total,
 *   sensor_timestamp_us,gps_timestamp_us,gps_latitude_e7,
 *   gps_longitude_e7,gps_altitude_mm,value_0,...,value_295
 *
 * Each subsequent row is one sensor_record.
 *
 * On success: returns 0, *records_out points to a dynamically
 * allocated array of count records, *count_out holds the count.
 * Caller must free with free_csv_records().
 *
 * On failure: returns nonzero, error_buf is populated (null-terminated
 * if error_buf_size > 0). *records_out and *count_out are left
 * untouched.
 */
int read_csv_records(const char *path,
                     struct sensor_record **records_out,
                     size_t *count_out,
                     char *error_buf,
                     size_t error_buf_size);

/* Free an array of records allocated by read_csv_records. */
void free_csv_records(struct sensor_record *records);

#endif /* CSV_READER_H */
