/**
 * Server made specifically for AirOS firmware. There's a special file,
 * `/proc/gpio/system_led`, that is able to control the device's GPIO.
 * Said file reads lines, one at a time, containing three space-separated
 * integers. The first integer is the bit, the GPIO pin the command will
 * alter. The second and third integers are only booleans, controlling wether
 * the pin's direction (input/output) and its value (on/off), but I don't
 * know in which order. For example, to turn the pin 5 on:
 *
 *     echo 5 1 1 > /proc/gpio/system_led
 *
 * Some pins are reserved by the system or kernel modules. To unreserve the
 * four signal level LEDs, do `rmmod rssi-leds` first. Their pin IDs are
 * 0, 1, 11, 7. I haven't managed to unreserve the other two LEDs yet.
 **/

#include "server.h"

typedef struct server_data {
  int control_fd;
} server_data;

void handle_message(void *opaque, const ledp_packet* packet) {
  server_data *data = opaque;

  // Prepare commands
  char commands [7*32];
  size_t commands_length = 0;
  size_t i;
  for (i = 0; i < 32; i++) {
    if (!(packet->mask & (1 << i))) continue;
    int value = !!(packet->values & (1 << i));
    commands_length += sprintf(commands + commands_length, "%u %d %d\n", i, value, value);
  }

  // Directly using UNIX I/O is better here
  size_t written = write(data->control_fd, commands, commands_length);
  assert(written == commands_length);
}

int main(int argc, char **argv) {
  // Open AirOS-specific LED control file
  server_data data;
  data.control_fd = open("/proc/gpio/system_led", O_WRONLY);
  assert(data.control_fd != -1);

  // Start LEDP server
  int status = start_ledp_server(DEFAULT_PORT_STRING, handle_message, &data);
  if (status) return 1;

  // Close files
  status = close(data.control_fd);
  assert(!status);
  return 0;
}
