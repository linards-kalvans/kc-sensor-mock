#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "csv_reader.h"
#include "serialize.h"
#include "tcp_client.h"

static void print_usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s --csv <csv_file> --emit-binary <output_file>\n"
        "       %s --csv <csv_file> --host <host> --port <port>\n"
        "\n"
        "Read CSV sensor records and emit concatenated wire-format binary.\n"
        "  --csv <path>        Path to CSV input file (required)\n"
        "  --emit-binary <out> Path to write serialized binary records\n"
        "  --host <host>       TCP host to connect to (send mode)\n"
        "  --port <port>       TCP port to connect to (send mode)\n",
        prog, prog);
}

int main(int argc, char *argv[]) {
    const char *csv_path = NULL;
    const char *emit_path = NULL;
    const char *host = NULL;
    long port_long = -1;

    /* Minimal argv parsing */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--csv") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --csv requires a path argument\n");
                print_usage(argv[0]);
                return 1;
            }
            csv_path = argv[++i];
        } else if (strcmp(argv[i], "--emit-binary") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --emit-binary requires a path argument\n");
                print_usage(argv[0]);
                return 1;
            }
            emit_path = argv[++i];
        } else if (strcmp(argv[i], "--host") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --host requires a host argument\n");
                print_usage(argv[0]);
                return 1;
            }
            host = argv[++i];
        } else if (strcmp(argv[i], "--port") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --port requires a port argument\n");
                print_usage(argv[0]);
                return 1;
            }
            char *end;
            errno = 0;
            port_long = strtol(argv[++i], &end, 10);
            if (*end != '\0' || errno != 0 || port_long <= 0 || port_long > 65535) {
                fprintf(stderr, "Error: --port must be in range 1-65535\n");
                print_usage(argv[0]);
                return 1;
            }
        } else {
            fprintf(stderr, "Error: unknown option '%s'\n", argv[i]);
            print_usage(argv[0]);
            return 1;
        }
    }

    if (csv_path == NULL) {
        fprintf(stderr, "Error: --csv is required\n");
        print_usage(argv[0]);
        return 1;
    }

    /* Validate send-mode completeness: --host and --port must both be present */
    int host_given = host != NULL;
    int port_given = port_long > 0;

    if (host_given && !port_given) {
        fprintf(stderr, "Error: --host requires --port\n");
        print_usage(argv[0]);
        return 1;
    }
    if (port_given && !host_given) {
        fprintf(stderr, "Error: --port requires --host\n");
        print_usage(argv[0]);
        return 1;
    }

    /* Exactly one output mode required */
    int emit_given = emit_path != NULL;
    int send_given = host_given && port_given;

    if (!emit_given && !send_given) {
        fprintf(stderr, "Error: --emit-binary or --host/--port is required\n");
        print_usage(argv[0]);
        return 1;
    }

    if (emit_given && send_given) {
        fprintf(stderr, "Error: --emit-binary and --host/--port are mutually exclusive\n");
        print_usage(argv[0]);
        return 1;
    }

    /* Read CSV records */
    struct sensor_record *records = NULL;
    size_t count = 0;
    char errbuf[512];

    int rc = read_csv_records(csv_path, &records, &count, errbuf, sizeof(errbuf));
    if (rc != 0) {
        fprintf(stderr, "Error: %s\n", errbuf);
        return 1;
    }

    uint8_t buf[SENSOR_RECORD_SIZE];

    if (emit_given) {
        /* File output mode */
        FILE *out = fopen(emit_path, "wb");
        if (!out) {
            fprintf(stderr, "Error: cannot open %s for writing: %s\n",
                    emit_path, strerror(errno));
            free_csv_records(records);
            return 1;
        }

        for (size_t i = 0; i < count; i++) {
            char ser_err[256];
            int sret = serialize_record(&records[i], buf, ser_err, sizeof(ser_err));
            if (sret != 0) {
                fprintf(stderr, "Error: failed to serialize record %zu: %s\n",
                        i, ser_err);
                fclose(out);
                free_csv_records(records);
                return 1;
            }
            size_t written = fwrite(buf, 1, SENSOR_RECORD_SIZE, out);
            if (written != SENSOR_RECORD_SIZE) {
                fprintf(stderr, "Error: short write on record %zu (%u/%u bytes)\n",
                        i, (unsigned)written, (unsigned)SENSOR_RECORD_SIZE);
                fclose(out);
                free_csv_records(records);
                return 1;
            }
        }

        if (fclose(out) != 0) {
            fprintf(stderr, "Error: failed to close output file: %s\n", strerror(errno));
            free_csv_records(records);
            return 1;
        }
    } else {
        /* TCP send mode — one connection, all records */
        char tcp_err[512];
        int tret = send_records_to_endpoint(host, (uint16_t)port_long,
                                            records, count,
                                            tcp_err, sizeof(tcp_err));
        if (tret != 0) {
            fprintf(stderr, "Error: %s\n", tcp_err);
            free_csv_records(records);
            return 1;
        }
    }

    free_csv_records(records);
    return 0;
}
