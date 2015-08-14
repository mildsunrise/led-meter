/**
 * Implemenents a simple LEDP server that calls a user-supplied
 * function whenever a valid LEDP message arrives.
 * This is the common logic used by the actual servers.
 **/

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <netdb.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#define DEFAULT_PORT 5021
#define DEFAULT_PORT_STRING "5021"
#define PROTOCOL_VERSION 1

typedef struct ledp_packet {
  uint8_t protocol_version;
  uint32_t mask;
  uint32_t values;
} ledp_packet;

static int __initialize_socket(const char *port) {
  int status;
  struct addrinfo hints, *addresses, *a;
  int sock;

  // Get possible addresses to bind to
  memset(&hints, 0x00, sizeof(hints));
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_DGRAM;
  hints.ai_flags = AI_PASSIVE;
  status = getaddrinfo(NULL, port, &hints, &addresses);
  if (status != 0) {
    fprintf(stderr, "Couldn't get address to bind to.\n");
    return -1;
  }

  // Try to create and bind our socket
  for (a = addresses; a; a = a->ai_next) {
    sock = socket(a->ai_family, a->ai_socktype, a->ai_protocol);
    if (sock == -1) continue;

    if (!bind(sock, a->ai_addr, a->ai_addrlen)) break;
    status = close(sock);
    assert(!status);
  }
  freeaddrinfo(addresses);

  if (!a) {
    fprintf(stderr, "Couldn't bind socket\n");
    return -1;
  }
  return sock;
}

static int start_ledp_server(const char *port, void (*handler)(void *opaque, const ledp_packet *packet), void *opaque) {
  // Create and bind a socket
  int sock = __initialize_socket(port);
  if (sock == -1) return 1;

  // Accept, validate and process messages
  while (1) {
    char received [9];
    ledp_packet packet;
    if (recv(sock, &received, 9, 0) != 9)
      continue;

    packet.protocol_version = *(uint8_t*)(received+0);
    if (packet.protocol_version != PROTOCOL_VERSION)
      continue;
    packet.mask = htonl(*(uint32_t*)(received+1));
    packet.values = htonl(*(uint32_t*)(received+5));
    handler(opaque, &packet);
  }

  // Close the socket
  if (close(sock)) return 1;
  return 0;
}
