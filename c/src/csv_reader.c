#define _POSIX_C_SOURCE 200809L

#include "csv_reader.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
#include <errno.h>
#include <limits.h>

#define EXPECTED_HEADER \
    "device_id,measurement_type,sequence_number,dropped_records_total," \
    "sensor_timestamp_us,gps_timestamp_us,gps_latitude_e7," \
    "gps_longitude_e7,gps_altitude_mm," \
    "value_0,value_1,value_2,value_3,value_4,value_5,value_6,value_7," \
    "value_8,value_9,value_10,value_11,value_12,value_13,value_14,value_15," \
    "value_16,value_17,value_18,value_19,value_20,value_21,value_22,value_23," \
    "value_24,value_25,value_26,value_27,value_28,value_29,value_30,value_31," \
    "value_32,value_33,value_34,value_35,value_36,value_37,value_38,value_39," \
    "value_40,value_41,value_42,value_43,value_44,value_45,value_46,value_47," \
    "value_48,value_49,value_50,value_51,value_52,value_53,value_54,value_55," \
    "value_56,value_57,value_58,value_59,value_60,value_61,value_62,value_63," \
    "value_64,value_65,value_66,value_67,value_68,value_69,value_70,value_71," \
    "value_72,value_73,value_74,value_75,value_76,value_77,value_78,value_79," \
    "value_80,value_81,value_82,value_83,value_84,value_85,value_86,value_87," \
    "value_88,value_89,value_90,value_91,value_92,value_93,value_94,value_95," \
    "value_96,value_97,value_98,value_99,value_100,value_101,value_102,value_103," \
    "value_104,value_105,value_106,value_107,value_108,value_109,value_110," \
    "value_111,value_112,value_113,value_114,value_115,value_116,value_117," \
    "value_118,value_119,value_120,value_121,value_122,value_123,value_124," \
    "value_125,value_126,value_127,value_128,value_129,value_130,value_131," \
    "value_132,value_133,value_134,value_135,value_136,value_137,value_138," \
    "value_139,value_140,value_141,value_142,value_143,value_144,value_145," \
    "value_146,value_147,value_148,value_149,value_150,value_151,value_152," \
    "value_153,value_154,value_155,value_156,value_157,value_158,value_159," \
    "value_160,value_161,value_162,value_163,value_164,value_165,value_166," \
    "value_167,value_168,value_169,value_170,value_171,value_172,value_173," \
    "value_174,value_175,value_176,value_177,value_178,value_179,value_180," \
    "value_181,value_182,value_183,value_184,value_185,value_186,value_187," \
    "value_188,value_189,value_190,value_191,value_192,value_193,value_194," \
    "value_195,value_196,value_197,value_198,value_199,value_200,value_201," \
    "value_202,value_203,value_204,value_205,value_206,value_207,value_208," \
    "value_209,value_210,value_211,value_212,value_213,value_214,value_215," \
    "value_216,value_217,value_218,value_219,value_220,value_221,value_222," \
    "value_223,value_224,value_225,value_226,value_227,value_228,value_229," \
    "value_230,value_231,value_232,value_233,value_234,value_235,value_236," \
    "value_237,value_238,value_239,value_240,value_241,value_242,value_243," \
    "value_244,value_245,value_246,value_247,value_248,value_249,value_250," \
    "value_251,value_252,value_253,value_254,value_255,value_256,value_257," \
    "value_258,value_259,value_260,value_261,value_262,value_263,value_264," \
    "value_265,value_266,value_267,value_268,value_269,value_270,value_271," \
    "value_272,value_273,value_274,value_275,value_276,value_277,value_278," \
    "value_279,value_280,value_281,value_282,value_283,value_284,value_285," \
    "value_286,value_287,value_288,value_289,value_290,value_291,value_292," \
    "value_293,value_294,value_295"

#define TOTAL_COLUMNS 305
#define META_COLUMNS 9
#define VALUE_COLUMNS 296

static void format_error(char *buf, size_t buf_size, const char *msg) {
    if (buf && buf_size > 0) {
        snprintf(buf, buf_size, "%s", msg);
    }
}

/*
 * Split a line on commas.  Unlike strtok_r, this preserves empty fields
 * (two adjacent commas produce an empty-string token).  Tokens point into
 * the original line buffer.  Returns the number of tokens written (at most
 * max_tokens).  If the line has more than max_tokens comma-separated fields,
 * *overflow is set to the number of excess fields (the count of additional
 * commas beyond max_tokens-1).
 */
static int split_csv_line(char *line, char tokens[][4096], int max_tokens,
                          int *overflow) {
    int count = 0;
    char *start = line;

    if (overflow) *overflow = 0;

    /* Count commas before we mutates the line */
    int commas = 0;
    {
        char *p = line;
        while (*p) {
            if (*p == ',') commas++;
            p++;
        }
    }

    while (*start) {
        char *comma = strchr(start, ',');
        if (comma) {
            if (count < max_tokens) {
                *comma = '\0';
                strncpy(tokens[count], start, 4095);
                tokens[count][4095] = '\0';
                count++;
            } else {
                /* overflow: stop consuming tokens, just skip to end */
                break;
            }
            start = comma + 1;
        } else {
            /* last token */
            if (count < max_tokens) {
                strncpy(tokens[count], start, 4095);
                tokens[count][4095] = '\0';
                count++;
            }
            break;
        }
    }

    /* Compute overflow: excess fields beyond max_tokens */
    if (overflow) {
        /* commas == fields - 1; excess = commas - (max_tokens - 1) */
        int excess = commas - (max_tokens - 1);
        if (excess > 0) *overflow = excess;
    }

    return count;
}

int read_csv_records(const char *path,
                     struct sensor_record **records_out,
                     size_t *count_out,
                     char *error_buf,
                     size_t error_buf_size) {
    if (!path || !records_out || !count_out || error_buf_size == 0) {
        format_error(error_buf, error_buf_size, "NULL argument");
        return 1;
    }

    FILE *fp = fopen(path, "r");
    if (!fp) {
        char msg[128];
        snprintf(msg, sizeof(msg), "fopen: %s: %s", path, strerror(errno));
        format_error(error_buf, error_buf_size, msg);
        return 1;
    }

   char *line = NULL;
    size_t line_cap = 0;
    ssize_t line_len;
    int line_no = 0;
    size_t capacity = 0;
    size_t count = 0;
    struct sensor_record *records = NULL;
    int header_seen = 0;

    while ((line_len = getline(&line, &line_cap, fp)) != -1) {
        line_no++;

        /* Strip trailing newline/carriage-return */
        while (line_len > 0 &&
               (line[line_len - 1] == '\n' || line[line_len - 1] == '\r')) {
            line[--line_len] = '\0';
        }

        /* Skip empty lines */
        if (line_len == 0) {
            continue;
        }

        /* Header line */
        if (line_no == 1) {
            if (strcmp(line, EXPECTED_HEADER) != 0) {
                format_error(error_buf, error_buf_size,
                              "line 1: header mismatch");
                free(line);
                fclose(fp);
                return 1;
            }
            header_seen = 1;
            continue;
        }

        /* Data line: split on commas, preserving empty fields */
        char tokens[TOTAL_COLUMNS][4096];
        int overflow = 0;
        int token_count = split_csv_line(line, tokens, TOTAL_COLUMNS, &overflow);
        if (overflow > 0) {
            char msg[256];
            snprintf(msg, sizeof(msg),
                      "line %d: too many columns (%d extra)",
                      line_no, overflow);
            format_error(error_buf, error_buf_size, msg);
            free(line);
            fclose(fp);
            return 1;
        }
        if (token_count != TOTAL_COLUMNS) {
            char msg[256];
            snprintf(msg, sizeof(msg),
                      "line %d: expected %d columns, got %d",
                      line_no, TOTAL_COLUMNS, token_count);
            format_error(error_buf, error_buf_size, msg);
            free(line);
            fclose(fp);
            return 1;
        }

        /* Grow record array */
        if (count >= capacity) {
            size_t new_cap = capacity == 0 ? 16 : capacity * 2;
            struct sensor_record *tmp = realloc(records, new_cap * sizeof(*records));
            if (!tmp) {
                format_error(error_buf, error_buf_size, "realloc failed");
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            records = tmp;
            capacity = new_cap;
        }

        struct sensor_record *rec = &records[count];
        memset(rec, 0, sizeof(*rec));

        /* Parse metadata fields (cols 0..8) */
        {
            unsigned long long v;
            char *end;
            int col = 0;

            /* device_id: uint16 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (device_id): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            v = strtoull(tokens[col], &end, 10);
            if (*end != '\0' || v > 0xFFFF) {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (device_id): out of uint16 range", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->device_id = (uint16_t)v;
            col++;

            /* measurement_type: uint16 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (measurement_type): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            v = strtoull(tokens[col], &end, 10);
            if (*end != '\0' || v > 0xFFFF) {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (measurement_type): out of uint16 range", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            if (v != MEASUREMENT_TYPE_SPECTRA && v != MEASUREMENT_TYPE_BACKGROUND_SPECTRA) {
                char msg[256];
                snprintf(msg, sizeof(msg),
                         "line %d col %d (measurement_type): must be 1 (spectra) or 2 (background spectra), got %llu",
                         line_no, col, (unsigned long long)v);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->measurement_type = (uint16_t)v;
            col++;

            /* sequence_number: uint32 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (sequence_number): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            v = strtoull(tokens[col], &end, 10);
            if (*end != '\0' || v > 0xFFFFFFFFULL) {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (sequence_number): out of uint32 range", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->sequence_number = (uint32_t)v;
            col++;

            /* dropped_records_total: uint32 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (dropped_records_total): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            v = strtoull(tokens[col], &end, 10);
            if (*end != '\0' || v > 0xFFFFFFFFULL) {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (dropped_records_total): out of uint32 range", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->dropped_records_total = (uint32_t)v;
            col++;

            /* sensor_timestamp_us: uint64 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (sensor_timestamp_us): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            errno = 0;
            v = strtoull(tokens[col], &end, 10);
            if (errno == ERANGE || *end != '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (sensor_timestamp_us): parse error", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->sensor_timestamp_us = (uint64_t)v;
            col++;

            /* gps_timestamp_us: uint64 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (gps_timestamp_us): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            errno = 0;
            v = strtoull(tokens[col], &end, 10);
            if (errno == ERANGE || *end != '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (gps_timestamp_us): parse error", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            rec->gps_timestamp_us = (uint64_t)v;
            col++;

            /* gps_latitude_e7: int32 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (gps_latitude_e7): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            {
                long long iv;
                char *end2;
                iv = strtoll(tokens[col], &end2, 10);
                if (*end2 != '\0') {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_latitude_e7): parse error", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                if (iv < INT32_MIN || iv > INT32_MAX) {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_latitude_e7): out of int32 range", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                rec->gps_latitude_e7 = (int32_t)iv;
            }
            col++;

            /* gps_longitude_e7: int32 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (gps_longitude_e7): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            {
                long long iv;
                char *end4;
                iv = strtoll(tokens[col], &end4, 10);
                if (*end4 != '\0') {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_longitude_e7): parse error", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                if (iv < INT32_MIN || iv > INT32_MAX) {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_longitude_e7): out of int32 range", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                rec->gps_longitude_e7 = (int32_t)iv;
            }
            col++;

            /* gps_altitude_mm: int32 */
            if (tokens[col][0] == '\0') {
                char msg[256];
                snprintf(msg, sizeof(msg), "line %d col %d (gps_altitude_mm): empty field", line_no, col);
                format_error(error_buf, error_buf_size, msg);
                free(line);
                free(records);
                fclose(fp);
                return 1;
            }
            {
                long long iv;
                char *end6;
                iv = strtoll(tokens[col], &end6, 10);
                if (*end6 != '\0') {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_altitude_mm): parse error", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                if (iv < INT32_MIN || iv > INT32_MAX) {
                    char msg[256];
                    snprintf(msg, sizeof(msg), "line %d col %d (gps_altitude_mm): out of int32 range", line_no, col);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                rec->gps_altitude_mm = (int32_t)iv;
            }
        }

        /* Value columns: value_0..value_295, all uint16 */
        {
            char *vend;
            int col = META_COLUMNS;
            for (int i = 0; i < VALUE_COLUMNS; i++) {
                if (tokens[col][0] == '\0') {
                    char msg[256];
                    snprintf(msg, sizeof(msg),
                             "line %d col %d (value_%d): empty field",
                             line_no, col, i);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                unsigned long long v = strtoull(tokens[col], &vend, 10);
                if (*vend != '\0' || v > 0xFFFF) {
                    char msg[256];
                    snprintf(msg, sizeof(msg),
                             "line %d col %d (value_%d): out of uint16 range",
                             line_no, col, i);
                    format_error(error_buf, error_buf_size, msg);
                    free(line);
                    free(records);
                    fclose(fp);
                    return 1;
                }
                rec->values[i] = (uint16_t)v;
                col++;
            }
        }

        count++;
    }

    free(line);
    fclose(fp);

    /* Require at least one header row */
    if (!header_seen) {
        format_error(error_buf, error_buf_size, "no header row found");
        free_csv_records(records);
        return 1;
    }

    *records_out = records;
    *count_out = count;
    return 0;
}

void free_csv_records(struct sensor_record *records) {
    free(records);
}
