#!/usr/bin/python
"""
This module implements a LEDP client. The single class exported has
a low-level, stateless method to send a single message (`send_raw`),
and high-level methods (`sed_led`, `release_led`, `reset` and `commit`).
"""

import struct

protocol_version = 1
default_port = 5021

class Client:
    """
    Encodes and sends LEDP messages over a given socket.
    """

    def __init__(self, sock, hostname, port=default_port):
        """
        Initializes a LEDP client that will send messages through the
        user-supplied socket `sock`, which is expected to be in datagram mode.
        Messages will be sent to `hostname` and `port`.
        """
        self.sock = sock
        self.hostname = hostname
        self.port = port
        self.mask = int(0)
        self.values = int(0)

    def send_raw(self, mask, values):
        """
        Low-level method. Encodes and sends a LEDP message
        with `mask` and `values` supplied.
        """
        packet = struct.pack("!BII", protocol_version, mask, values)
        self.sock.sendto(packet, (self.hostname, self.port))

    def set_led(self, id, value):
        """
        Acquire and set a LED to a state.
        This does *not* send the command, see `commit()`.
        """
        self.mask |= (1 << id)
        if value:
            self.values |= (1 << id)
        else:
            self.values &= ~(1 << id)

    def release_led(self, id):
        """
        Release a LED. Future commits won't change the value of this LED.
        """
        self.mask &= ~(1 << id)

    def reset(self):
        """
        Release all LEDs. From now on, commits won't touch any LEDs until
        they are set again. This has the same effect as constructing a
        new instance.
        """
        self.mask = int(0)

    def commit(self):
        """
        Send a LEDP message to the device to update the state of the LEDs
        that have been touched via `set_led()` at least once.

        You may want to call this method multiple times to resend the message,
        just in case some packets get lost.
        """
        self.send_raw(self.mask, self.values)



if __name__ == "__main__":
    __doc__ = """
Simple LEDP client, sends a LEDP message to the specified host.

`<bits>` is a string of characters, which can be `0` (in which case, the
LED is turned off), `1` (the LED is turned on) or anything else (the LED
is not touched). The first character is the LED 0, the next is the
LED 1, and the string needn't have all 32 characters present. Examples:

Turn off LEDs 2 and 6, turn on LED 3:
  ledp.py 192.168.1.6 __01__0

Usage:
  ledp.py [options] <hostname:port> <bits>
  ledp.py (-h | --help)

Options:
  -r <n>, --redundancy <n>  How many times to send the message. [default: 1]
    """

    import socket

    from docopt import docopt
    arguments = docopt(__doc__.strip())

    # Create client
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    host = arguments["<hostname:port>"].split(":")
    if len(host) > 2:
        raise Exception("invalid host given")
    if len(host) == 2:
        client = Client(sock, host[0], int(host[1]))
    else:
        client = Client(sock, host[0])

    # Set LEDs
    bits = arguments["<bits>"]
    if len(bits) > 32:
        raise Exception("Invalid bits pattern given")

    for pos, value in enumerate(bits):
        if value == "0":
            client.set_led(pos, False)
        if value == "1":
            client.set_led(pos, True)

    # Send messages
    redundancy = int(arguments["--redundancy"])
    for i in xrange(redundancy):
        client.commit()

    # Close
    sock.close()
