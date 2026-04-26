CC ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -Iinclude
BUILD_DIR := build
BIN_DIR := bin

.PHONY: clean all test-serializer test-csv-parser

$(BUILD_DIR) $(BIN_DIR):
	mkdir -p $@

all: $(BIN_DIR)/c-producer

$(BIN_DIR)/c-producer: $(BUILD_DIR)/main.o $(BUILD_DIR)/serialize.o $(BUILD_DIR)/csv_reader.o $(BUILD_DIR)/tcp_client.o | $(BIN_DIR)
	$(CC) $(CFLAGS) $^ -o $@

$(BUILD_DIR)/%.o: src/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

test-serializer: | $(BUILD_DIR)
	$(CC) $(CFLAGS) tests/test_serialize.c src/serialize.c -o $(BUILD_DIR)/test_serialize
	$(BUILD_DIR)/test_serialize

test-csv-parser: | $(BUILD_DIR)
	$(CC) $(CFLAGS) tests/test_csv_reader.c src/csv_reader.c -o $(BUILD_DIR)/test_csv_parser
	$(BUILD_DIR)/test_csv_parser

clean:
	rm -rf $(BUILD_DIR) $(BIN_DIR)
