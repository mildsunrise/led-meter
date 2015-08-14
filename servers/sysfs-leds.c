/**
 * Server that exports the LEDs available in `/sys/class/leds`.
 * Especially indicated for OpenWRT or modern linuxes.
 **/

#include "server.h"
#include <dirent.h>

typedef struct led_entry {
  int brightness_fd;
  int max_brightness;
} led_entry;

typedef struct server_data {
  led_entry *entries;
  size_t entries_count;
  size_t entries_found;
} server_data;

void handle_message(void *opaque, const ledp_packet *packet) {
  server_data *data = opaque;

  size_t led;
  for (led = 0; led < data->entries_count; led++) {
    if (!(packet->mask & (1 << led))) continue;

    led_entry *entry = &data->entries[led];
    int value = (packet->values & (1 << led)) ? entry->max_brightness : 0;

    // Directly using UNIX I/O is better here
    char line [16];
    size_t line_length = sprintf(line, "%d\n", value);
    size_t written = write(entry->brightness_fd, line, line_length);
    assert(written == line_length);
  }
}

int process_led(server_data *data, const char *name) {
  char path [288];
  int name_length = strlen(name);
  memcpy(path, name, name_length);

  // Append entry if possible
  data->entries_found++;
  if (data->entries_count >= 32)
    return 1;
  led_entry *entry = &data->entries[data->entries_count++];

  // Scan LED's max brightness
  path[name_length] = 0;
  strcat(path, "/max_brightness");
  FILE *mbfile = fopen(path, "r");
  if (!mbfile) {
    fprintf(stderr, "Couldn't open %s for reading\n", path);
    return 1;
  }
  if (fscanf(mbfile, "%d", &entry->max_brightness) < 1) {
    fprintf(stderr, "Couldn't scan max brightness of LED %s\n", name);
    return 1;
  }

  // Open control file
  path[name_length] = 0;
  strcat(path, "/brightness");
  entry->brightness_fd = open(path, O_WRONLY);
  if (entry->brightness_fd == -1) {
    fprintf(stderr, "Couldn't open %s for writing\n", path);
    return 1;
  }

  return 0;
}

int main(int argc, char **argv) {
  int status;
  server_data data;

  // List available LEDs
  size_t lednames_count;
  struct dirent **lednames;
  status = chdir("/sys/class/leds");
  if (status) {
    fprintf(stderr, "Couldn't enter /sys/class/leds directory.\n");
    return 1;
  }
  status = scandir(".", &lednames, NULL, alphasort);
  if (status < 0) {
    fprintf(stderr, "Failed to scan /sys/class/leds for LEDs\n");
    return 1;
  }
  lednames_count = status;

  // Prepare data structure
  data.entries_count = data.entries_found = 0;
  data.entries = calloc(lednames_count, sizeof(led_entry));
  if (!data.entries) {
    fprintf(stderr, "Couldn't allocate space for LED entries\n");
    return 1;
  }

  // Process each LED, collect info and open control file
  size_t led;
  for (led = 0; led < lednames_count; led++) {
    if (strcmp(lednames[led]->d_name, ".") == 0 || strcmp(lednames[led]->d_name, "..") == 0)
      continue;
    status = process_led(&data, lednames[led]->d_name);
    if (status) return 1;

    free(lednames[led]);
  }
  free(lednames);

  if (data.entries_found > data.entries_count)
    fprintf(stderr, "Warning: %u LEDs found. Serving the first %u.\n", data.entries_found, data.entries_count);
  printf("Serving %u LEDs.\n", data.entries_count);

  // Start LEDP server
  status = start_ledp_server(DEFAULT_PORT_STRING, handle_message, &data);
  if (status) return 1;

  // Close files
  while (data.entries_count) {
    led_entry *entry = &data.entries[--data.entries_count];
    status = close(entry->brightness_fd);
    assert(!status);
  }
  free(data.entries);
  return 0;
}
