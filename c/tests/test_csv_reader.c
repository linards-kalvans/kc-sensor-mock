#define _POSIX_C_SOURCE 200809L

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sensor_record.h"
#include "csv_reader.h"

#define FIXTURE_PATH "../tests/c_fixtures/minimal_record.csv"
#define BAD_PATH "/nonexistent/path/bad.csv"

int main(void) {
    struct sensor_record *records = NULL;
    size_t count = 0;
    char errbuf[256];

    /* Test 1: nonexistent file returns error */
    errbuf[0] = '\0';
    int rc = read_csv_records(BAD_PATH, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: nonexistent file returns error: %s\n", errbuf);

    /* Test 2: valid fixture parses successfully */
    rc = read_csv_records(FIXTURE_PATH, &records, &count, errbuf, sizeof(errbuf));
    assert(rc == 0);
    assert(count == 1);
    printf("PASS: fixture parsed, count=%zu\n", count);

    /* Test 3: field values match fixture */
    assert(records[0].device_id == 4660);
    assert(records[0].measurement_type == 2);
    assert(records[0].sequence_number == 16909060);
    assert(records[0].dropped_records_total == 84281096);
    assert(records[0].sensor_timestamp_us == 72623859790382856ULL);
    assert(records[0].gps_timestamp_us == 1230066625199609624ULL);
    assert(records[0].gps_latitude_e7 == -123456789);
    assert(records[0].gps_longitude_e7 == 168496141);
    assert(records[0].gps_altitude_mm == -1000);
    assert(records[0].values[0] == 258);
    assert(records[0].values[1] == 772);
    assert(records[0].values[2] == 1541);
    assert(records[0].values[3] == 2055);
    /* remaining values are 0 */
    for (int i = 4; i < SENSOR_VALUES_COUNT; i++) {
        assert(records[0].values[i] == 0);
    }
    printf("PASS: field values match fixture\n");

    /* Test 4: free_csv_records does not crash */
    free_csv_records(records);
    records = NULL;
    printf("PASS: free_csv_records ok\n");

    /* Test 5: wrong header rejected */
    const char *tmpdir = getenv("TMPDIR");
    char tmppath[512];
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_bad_header.csv",
             tmpdir ? tmpdir : "/tmp");
    FILE *tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    fprintf(tmpf, "wrong,header,cols\n");
    fprintf(tmpf, "1,2,3\n");
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    printf("PASS: wrong header rejected: %s\n", errbuf);
    free_csv_records(records);

    remove(tmppath);

    /* Test 6: wrong column count (too few columns) rejected */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_bad_colcount.csv",
             tmpdir ? tmpdir : "/tmp");
    /* Copy fixture, then truncate data row to 5 columns */
    FILE *src = fopen(FIXTURE_PATH, "r");
    assert(src != NULL);
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    char *line = NULL;
    size_t line_cap = 0;
    ssize_t nread;
    int lineno = 0;
    while ((nread = getline(&line, &line_cap, src)) != -1) {
        lineno++;
        if (lineno == 1) {
            /* write header unchanged */
            fwrite(line, 1, nread, tmpf);
        } else {
            /* data row: replace with 5-column row */
            fprintf(tmpf, "1,2,3,4,5\n");
        }
    }
    free(line);
    fclose(src);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: wrong column count rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    /* Test 7: empty field (missing token) in data row rejected */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_empty_field.csv",
             tmpdir ? tmpdir : "/tmp");
    src = fopen(FIXTURE_PATH, "r");
    assert(src != NULL);
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    line = NULL;
    line_cap = 0;
    lineno = 0;
    while ((nread = getline(&line, &line_cap, src)) != -1) {
        lineno++;
        if (lineno == 1) {
            fwrite(line, 1, nread, tmpf);
        } else {
            /* data row: set gps_timestamp_us (col 6) to empty field */
            fprintf(tmpf,
                "4660,2,16909060,84281096,72623859790382856,,0,168496141,-1000,");
            for (int i = 0; i < SENSOR_VALUES_COUNT; i++) {
                if (i > 0) fprintf(tmpf, ",");
                fprintf(tmpf, "0");
            }
            fprintf(tmpf, "\n");
        }
    }
    free(line);
    fclose(src);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: empty field rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    /* Test 8: empty file rejected */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_empty.csv",
              tmpdir ? tmpdir : "/tmp");
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: empty file rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    /* Test 9: row with 306 columns (overflow) rejected */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_overflow.csv",
              tmpdir ? tmpdir : "/tmp");
    /* Copy fixture header (305 cols), then write a data row with 306 fields */
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    src = fopen(FIXTURE_PATH, "r");
    assert(src != NULL);
    line = NULL;
    line_cap = 0;
    lineno = 0;
    while ((nread = getline(&line, &line_cap, src)) != -1) {
        lineno++;
        if (lineno == 1) {
            /* write the correct 305-col header unchanged */
            fwrite(line, 1, nread, tmpf);
        } else {
            /* data row: 306 comma-separated fields (one extra value) */
            fprintf(tmpf, "4660,2,16909060,84281096,72623859790382856,");
            fprintf(tmpf, "1230066625199609624,-123456789,168496141,-1000,");
            for (int i = 0; i < 297; i++) {
                if (i > 0) fprintf(tmpf, ",");
                fprintf(tmpf, "0");
            }
            fprintf(tmpf, "\n");
        }
    }
    free(line);
    fclose(src);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: 306-column row rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    /* Test 10: uint64 overflow in sensor_timestamp_us rejected */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_uint64_overflow.csv",
             tmpdir ? tmpdir : "/tmp");
    src = fopen(FIXTURE_PATH, "r");
    assert(src != NULL);
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    line = NULL;
    line_cap = 0;
    lineno = 0;
    while ((nread = getline(&line, &line_cap, src)) != -1) {
        lineno++;
        if (lineno == 1) {
            fwrite(line, 1, nread, tmpf);
        } else {
            /* data row: set sensor_timestamp_us to 18446744073709551616
             * (UINT64_MAX + 1, which is 20 digits, larger than any uint64) */
            fprintf(tmpf,
                "4660,2,16909060,84281096,18446744073709551616,");
            fprintf(tmpf, "1230066625199609624,-123456789,168496141,-1000,");
            for (int i = 0; i < SENSOR_VALUES_COUNT; i++) {
                if (i > 0) fprintf(tmpf, ",");
                fprintf(tmpf, "0");
            }
            fprintf(tmpf, "\n");
        }
    }
    free(line);
    fclose(src);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: uint64 overflow rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    /* Test 11: NULL argument rejected */
    errbuf[0] = '\0';
    rc = read_csv_records(NULL, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: NULL path rejected: %s\n", errbuf);

    /* Test 12: invalid measurement_type rejected (not 1 or 2) */
    snprintf(tmppath, sizeof(tmppath), "%s/csv_test_bad_meas_type.csv",
              tmpdir ? tmpdir : "/tmp");
    src = fopen(FIXTURE_PATH, "r");
    assert(src != NULL);
    tmpf = fopen(tmppath, "w");
    assert(tmpf != NULL);
    line = NULL;
    line_cap = 0;
    lineno = 0;
    while ((nread = getline(&line, &line_cap, src)) != -1) {
        lineno++;
        if (lineno == 1) {
            fwrite(line, 1, nread, tmpf);
        } else {
            /* data row: set measurement_type to 99 (invalid) */
            fprintf(tmpf,
                "4660,99,16909060,84281096,72623859790382856,");
            fprintf(tmpf, "1230066625199609624,-123456789,168496141,-1000,");
            for (int i = 0; i < SENSOR_VALUES_COUNT; i++) {
                if (i > 0) fprintf(tmpf, ",");
                fprintf(tmpf, "0");
            }
            fprintf(tmpf, "\n");
        }
    }
    free(line);
    fclose(src);
    fclose(tmpf);

    rc = read_csv_records(tmppath, &records, &count, errbuf, sizeof(errbuf));
    assert(rc != 0);
    assert(errbuf[0] != '\0');
    printf("PASS: invalid measurement_type rejected: %s\n", errbuf);
    free_csv_records(records);
    remove(tmppath);

    printf("ALL TESTS PASSED\n");
    return 0;
}

