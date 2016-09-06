/**
 * Server that connects to a wiimote and controls its 4 LEDs.
 * You need a bluetooth adapter and libcwiid1 installed to use this.
 * cc wiimote.c -Wall -Wextra -lcwiid -lbluetooth -o wiimote
 **/

#include <cwiid.h>
#include <bluetooth/bluetooth.h>
#include "server.h"

typedef struct server_data {
  cwiid_wiimote_t *wiimote;
  int leds;
} server_data;

void handle_message(void *opaque, const ledp_packet* packet) {
  server_data *data = opaque;
  data->leds &= ~packet->mask;
  data->leds |= packet->values;

  // Update Wiimote LEDs
  static int led_flags [] = { CWIID_LED1_ON, CWIID_LED2_ON, CWIID_LED3_ON, CWIID_LED4_ON };
  int flags = 0, i;
  for (i = 0; i < 4; i++)
    if (data->leds & (1 << i))
      flags |= led_flags[i];
  if (cwiid_set_led(data->wiimote, flags))
    fprintf(stderr, "Couldn't send command to Wiimote\n");
}

int print_help(const char *basename) {
  fprintf(stderr, "Usage: %s [<bdaddr> [<port>]]\n", basename);
  return 1;
}

int main(int argc, char **argv) {
  server_data data;
  bdaddr_t addr = *BDADDR_ANY;
  const char *port = DEFAULT_PORT_STRING;
  char addr_string [18];
  int status;

  // Parse args
  if (argc > 3) return print_help(argv[0]);
  if (argc >= 2) {
    if (str2ba(argv[1], &addr)) return print_help(argv[0]);
  }
  if (argc >= 3) {
    int t = atoi(argv[2]);
    if (t <= 0 || t >= 65536) return print_help(argv[0]);
    port = argv[2];
  }

  // Connect to the Wiimote
  printf("Connecting to Wiimote...\n");
  data.wiimote = cwiid_open(&addr, 0);
  if (!data.wiimote) {
    fprintf(stderr, "Couldn't connect to your beloved Wiimote. I'm sorry.\n");
    return 1;
  }
  status = ba2str(&addr, addr_string);
  assert(status);
  printf("Connected to %s\n", addr_string);

  // Start LEDP server
  data.leds = 0;
  status = start_ledp_server(port, handle_message, &data);
  if (status) return 1;

  // Disconnect
  status = cwiid_close(data.wiimote);
  assert(!status);
  return 0;
}
