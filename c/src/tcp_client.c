#define _POSIX_C_SOURCE 200809L

#include "tcp_client.h"
#include "serialize.h"

#include <errno.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/*
 * Send all bytes of buf over sockfd, retrying on EINTR.
 * Uses MSG_NOSIGNAL to avoid SIGPIPE on broken connections.
 */
static int send_all(int sockfd, const uint8_t *buf, size_t len, char *error_buf, size_t error_buf_size) {
    size_t sent = 0;
    while (sent < len) {
        ssize_t n = send(sockfd, buf + sent, len - sent, MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EINTR) continue;
            if (error_buf && error_buf_size > 0) {
                snprintf(error_buf, error_buf_size, "send failed at offset %zu", sent);
            }
            return 1;
        }
        if (n == 0) {
            if (error_buf && error_buf_size > 0) {
                snprintf(error_buf, error_buf_size, "send returned 0 at offset %zu", sent);
            }
            return 1;
        }
        sent += (size_t)n;
    }
    return 0;
}

int send_records_to_endpoint(const char *host, uint16_t port,
                             const struct sensor_record *records,
                             size_t count,
                             char *error_buf, size_t error_buf_size) {
    if (!host || !records || count == 0) {
        if (error_buf && error_buf_size > 0) {
            snprintf(error_buf, error_buf_size, "invalid arguments");
        }
        return 1;
    }
    if (error_buf_size == 0) {
        return 1;
    }

    struct addrinfo hints, *ai, *p;
    char portstr[8];
    snprintf(portstr, sizeof(portstr), "%u", (unsigned)port);

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    int rc = getaddrinfo(host, portstr, &hints, &ai);
    if (rc != 0) {
        if (error_buf && error_buf_size > 0) {
            snprintf(error_buf, error_buf_size, "getaddrinfo: %s", gai_strerror(rc));
        }
        return 1;
    }

    /* Open one connection, trying each addrinfo candidate */
    int sockfd = -1;
    for (p = ai; p != NULL; p = p->ai_next) {
        sockfd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (sockfd < 0) continue;

        if (connect(sockfd, p->ai_addr, p->ai_addrlen) == 0) break;
        close(sockfd);
        sockfd = -1;
    }

    freeaddrinfo(ai);

    if (sockfd < 0) {
        if (error_buf && error_buf_size > 0) {
            snprintf(error_buf, error_buf_size, "connect failed for %s:%u", host, (unsigned)port);
        }
        return 1;
    }

    /* Serialize and send all records over the single connection */
    uint8_t buf[SENSOR_RECORD_SIZE];
    for (size_t i = 0; i < count; i++) {
        int sret = serialize_record(&records[i], buf, error_buf, error_buf_size);
        if (sret != 0) {
            close(sockfd);
            return 1;
        }
        int serr = send_all(sockfd, buf, SENSOR_RECORD_SIZE, error_buf, error_buf_size);
        if (serr != 0) {
            close(sockfd);
            return 1;
        }
    }

    close(sockfd);
    return 0;
}
