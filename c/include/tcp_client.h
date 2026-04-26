#ifndef TCP_CLIENT_H
#define TCP_CLIENT_H

#include <stddef.h>
#include <stdint.h>

#include "sensor_record.h"

/*
 * Connect to host:port once, serialize and send all records over that
 * single connection, then close.
 *
 * On success: returns 0, all records fully transmitted.
 * On failure: returns nonzero, error_buf is populated.
 */
int send_records_to_endpoint(const char *host, uint16_t port,
                             const struct sensor_record *records,
                             size_t count,
                             char *error_buf, size_t error_buf_size);

#endif /* TCP_CLIENT_H */
