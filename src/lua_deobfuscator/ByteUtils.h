#ifndef BYTE_UTILS_H
#define BYTE_UTILS_H

#include <vector>
#include <cstdint>
#include <string>
#include <cstring>
#include <stdexcept>
#include <algorithm>

namespace lua_deobfuscator {

class ByteReader {
public:
    ByteReader(const std::vector<uint8_t>& data) : data(data), pos(0), little_endian(true) {}

    uint8_t read_byte() {
        if (pos >= data.size()) throw std::runtime_error("Unexpected end of data");
        return data[pos++];
    }

    std::vector<uint8_t> read_bytes(size_t n) {
        if (pos + n > data.size()) throw std::runtime_error("Unexpected end of data");
        std::vector<uint8_t> result(data.begin() + pos, data.begin() + pos + n);
        pos += n;
        return result;
    }

    int32_t read_int32(size_t size = 4) {
        std::vector<uint8_t> bytes = read_bytes(size);
        int32_t result = 0;
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) result |= (static_cast<int32_t>(bytes[i]) << (i * 8));
        } else {
            for (size_t i = 0; i < size; ++i) result = (result << 8) | bytes[i];
        }
        // Sign extend if necessary
        if (size < 4 && (bytes[size-1] & 0x80)) {
            for (size_t i = size; i < 4; ++i) result |= (0xFF << (i * 8));
        }
        return result;
    }

    uint32_t read_uint32(size_t size = 4) {
        std::vector<uint8_t> bytes = read_bytes(size);
        uint32_t result = 0;
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) result |= (static_cast<uint32_t>(bytes[i]) << (i * 8));
        } else {
            for (size_t i = 0; i < size; ++i) result = (result << 8) | bytes[i];
        }
        return result;
    }

    uint64_t read_uint64(size_t size = 8) {
        std::vector<uint8_t> bytes = read_bytes(size);
        uint64_t result = 0;
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) result |= (static_cast<uint64_t>(bytes[i]) << (i * 8));
        } else {
            for (size_t i = 0; i < size; ++i) result = (result << 8) | bytes[i];
        }
        return result;
    }

    int64_t read_int64(size_t size = 8) {
        uint64_t uval = read_uint64(size);
        return static_cast<int64_t>(uval);
    }

    double read_double(size_t size = 8) {
        std::vector<uint8_t> bytes = read_bytes(size);
        double result = 0;
        if (size == 8) {
            uint64_t uval = 0;
            if (little_endian) {
                for (size_t i = 0; i < 8; ++i) uval |= (static_cast<uint64_t>(bytes[i]) << (i * 8));
            } else {
                for (size_t i = 0; i < 8; ++i) uval = (uval << 8) | bytes[i];
            }
            std::memcpy(&result, &uval, 8);
        } else {
            uint32_t uval = 0;
            if (little_endian) {
                for (size_t i = 0; i < 4; ++i) uval |= (static_cast<uint32_t>(bytes[i]) << (i * 8));
            } else {
                for (size_t i = 0; i < 4; ++i) uval = (uval << 8) | bytes[i];
            }
            float fval;
            std::memcpy(&fval, &uval, 4);
            result = fval;
        }
        return result;
    }

    void set_endian(bool is_little) { little_endian = is_little; }
    size_t get_pos() const { return pos; }
    void seek(size_t new_pos) { pos = new_pos; }

private:
    const std::vector<uint8_t>& data;
    size_t pos;
    bool little_endian;
};

class ByteWriter {
public:
    ByteWriter() : little_endian(true) {}

    void write_byte(uint8_t b) { buffer.push_back(b); }

    void write_bytes(const std::vector<uint8_t>& bytes) {
        buffer.insert(buffer.end(), bytes.begin(), bytes.end());
    }

    void write_int32(int32_t val, size_t size = 4) {
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> (i * 8)) & 0xFF);
        } else {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> ((size - 1 - i) * 8)) & 0xFF);
        }
    }

    void write_uint32(uint32_t val, size_t size = 4) {
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> (i * 8)) & 0xFF);
        } else {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> ((size - 1 - i) * 8)) & 0xFF);
        }
    }

    void write_uint64(uint64_t val, size_t size = 8) {
        if (little_endian) {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> (i * 8)) & 0xFF);
        } else {
            for (size_t i = 0; i < size; ++i) buffer.push_back((val >> ((size - 1 - i) * 8)) & 0xFF);
        }
    }

    void write_double(double val, size_t size = 8) {
        if (size == 8) {
            uint64_t uval;
            std::memcpy(&uval, &val, 8);
            write_uint64(uval, 8);
        } else {
            float fval = static_cast<float>(val);
            uint32_t uval;
            std::memcpy(&uval, &fval, 4);
            write_uint32(uval, 4);
        }
    }

    void set_endian(bool is_little) { little_endian = is_little; }
    const std::vector<uint8_t>& get_data() const { return buffer; }

private:
    std::vector<uint8_t> buffer;
    bool little_endian;
};

} // namespace lua_deobfuscator

#endif // BYTE_UTILS_H
