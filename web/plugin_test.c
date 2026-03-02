#include <stdint.h>
#include <stdlib.h>

#define EXPORT __attribute__((visibility("default")))

int output_size = 0;
uint8_t* output_buffer = NULL;

EXPORT uint8_t* alloc_mem(int size) {
    return (uint8_t*)malloc(size);
}

EXPORT void free_mem(uint8_t* p) {
    free(p);
}

// Example plugin: invert all bytes
EXPORT uint8_t* process(uint8_t* input, int size) {
    if (output_buffer != NULL) {
        free(output_buffer);
    }

    output_buffer = (uint8_t*)malloc(size);
    output_size = size;

    for(int i = 0; i < size; i++) {
        output_buffer[i] = ~input[i];
    }

    return output_buffer;
}

EXPORT int get_size() {
    return output_size;
}
