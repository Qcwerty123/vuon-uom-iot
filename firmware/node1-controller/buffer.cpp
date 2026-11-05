#include "buffer.h"

static TelemetryRec ring[BUF_CAPACITY];  // ~18 KB RAM
static uint16_t head = 0;   // vị trí ghi tiếp theo
static uint16_t count = 0;
static uint32_t dropped = 0;

void bufPush(const TelemetryRec& rec) {
  ring[head] = rec;
  head = (head + 1) % BUF_CAPACITY;
  if (count < BUF_CAPACITY) {
    count++;
  } else {
    dropped++;  // vừa ghi đè bản cũ nhất
  }
}

bool bufPeek(TelemetryRec& out) {
  if (count == 0) return false;
  uint16_t tail = (head + BUF_CAPACITY - count) % BUF_CAPACITY;
  out = ring[tail];
  return true;
}

void bufPop() {
  if (count > 0) count--;
}

uint16_t bufCount() { return count; }
uint32_t bufDropped() { return dropped; }
