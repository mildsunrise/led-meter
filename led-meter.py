#!/usr/bin/python
"""
This module uses both parts, together with some logic to control
the device's LEDs from amplitude measures, and the JACK interface,
to provide the final CLI.
"""

import math


# Simple math utilities

def map(value, fr=(0, 1), to=(0, 1)):
    """
    Map a value from a two-value interval into another two-value interval.
    Both intervals are `(0, 1)` by default. Values outside the `fr` interval
    are still mapped proportionately.
    """
    value = (value - fr[0]) / (fr[1] - fr[0])
    return to[0] + value * (to[1] - to[0])

def clamp(value, start=0, end=1):
    """
    Clamp a number. If the number is inside the interval [start, end] it's
    returned unchanged. Otherwise, the nearest interval limit is returned.
    """
    if value > end: return end
    if value < start: return start
    return value

def to_decibel(value, limit=-70):
    """
    Convert a ratio to decibels. This method will never return less than the
    specified limit (default -70dB). If value is zero or negative, the limit
    will be returned as well.
    """
    if value > 0:
        db = 10 * math.log10(value)
        if db >= limit: return db
    return limit


# Logic that maps a single amplitude sample to a number of LEDs,
# and sends an apporpiate LEDP message to the device.

def map_to_leds(sample, options):
    """
    Map an amplitude measure (`sample`) into an integer, specifying how
    many LEDs should be turned on to represent that amplitude.
    `options` is a dictionary with the following keys:

    - `range` specifies the covered decibel range, a tuple of two numbers:
      the first one is the decibel measure that maps to zero LEDs turned on,
      while the second maps to all LEDs turned on.
    - `count` is the number of LEDs present; the returned value will always
      be between zero and `count`.
    - `should_round`: if true, the decibels will be rounded to the nearest
      number of LEDs instead of floored.
    """
    db = to_decibel(sample)
    meter = clamp(map(db, fr=options["range"])) * options["count"]

    if options["should_round"]:
        meter = round(meter)
    else:
        meter = math.floor(meter)

    return int(meter)

def send_leds(client, leds, count):
    """
    Given a LEDP client, a list of LEDs to turn on, and a count, turn the
    first `count` LEDs on, the rest off. No other LEDs are touched.
    `count` is expected to be an integer between zero and `len(leds)`.
    """
    for level, led_id in enumerate(leds):
        client.set_led(led_id, level < count)
    client.commit()



if __name__ == "__main__":
    __doc__ = """
LED-based JACK meter.

Usage:
  led-meter.py [options] <leds> <hostname:port>
  led-meter.py (-h | --help)
  led-meter.py --version

Metering options:
  -f <hz>, --framerate <hz>  How many volume updates to send per second. [default: 60]
  -s <db>, --map-start <db>  DB measure that maps to zero LEDs. [default: -18]
  -e <db>, --map-end <db>    DB measure that maps to all LEDs. [default: -4]
  --round                    Round the measure instead of flooring it.

Volume calculation options:
  -k <a>, --emphasis <e>     Opacity of the highpass (emphasis) filter. [default: 0.72]
  -c <hz>, --highpass <hz>   Highpass (emphasis) filter cutoff frequency. [default: 1.5]
  -a <ms>, --attack <ms>     Half-attack time for volume smoothing. [default: 2]
  -r <ms>, --release <ms>    Half-release time for volume smoothing. [default: 70]
  --envelope-cutoff <hz>     Cutoff frequency for the envelope follower. [default: 30]

JACK options:
  -n <name>, --name <name>    JACK client name to use. [default: led-meter]

General options:
  -h, --help     Show this help message.
  -v, --version  Show version information.
    """

    import numpy as np
    import jack
    import socket
    import ledp
    from filters import VolumeFollowFilter, AttackReleaseFilter

    from docopt import docopt
    arguments = docopt(__doc__.strip(), version="led-meter 0.1")

    # Create LEDP client
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(True)
    host = arguments["<hostname:port>"].split(":")
    if len(host) > 2:
        raise Exception("invalid host given")
    if len(host) == 2:
        client = ledp.Client(sock, host[0], int(host[1]))
    else:
        client = ledp.Client(sock, host[0])

    # Setup JACK interface
    jack.attach(arguments["--name"])
    jack.register_port("input", jack.IsInput | jack.IsTerminal | jack.IsPhysical)
    buffer_size = jack.get_buffer_size()
    sample_rate = jack.get_sample_rate()

    def buffer_size_callback():
        raise Exception("buffer size changed and I can't take that")
        exit(2)
    #jack.set_buffer_size_callback(buffer_size_callback) #FIXME
    def sample_rate_callback():
        raise Exception("sample rate changed and I can't take that")
        exit(2)
    #jack.set_sample_rate_callback(sample_rate_callback) #FIXME

    jack_input = np.zeros((1, buffer_size), 'f')
    jack_output = np.zeros((0, buffer_size), 'f')
    output_buffer = range(buffer_size)

    # Setup LED mapping & scheduling
    leds = list(int(id.strip()) for id in arguments["<leds>"].split(","))
    map_range = (float(arguments["--map-start"]), float(arguments["--map-end"]))
    should_round = arguments["--round"]
    map_options = {"range": map_range, "count": len(leds), "should_round": should_round}

    frame_rate = float(arguments["--framerate"])
    interval = int(round(sample_rate/frame_rate))

    # Create the audio filter
    time_to_frames = lambda time: float(time) * sample_rate

    envelope_cutoff_frequency = float(arguments["--envelope-cutoff"])
    envelope_cutoff_frames = time_to_frames(1 / envelope_cutoff_frequency)

    emphasis_opacity = float(arguments["--emphasis"])
    emphasis_cutoff_frequency = float(arguments["--highpass"])
    emphasis_cutoff_frames = time_to_frames(1 / emphasis_cutoff_frequency)

    smooth_attack_frames = time_to_frames(float(arguments["--attack"]) / 1000)
    smooth_attack_coefficient = AttackReleaseFilter.get_coefficient(smooth_attack_frames)
    smooth_release_frames = time_to_frames(float(arguments["--release"]) / 1000)
    smooth_release_coefficient = AttackReleaseFilter.get_coefficient(smooth_release_frames)

    volume_filter = VolumeFollowFilter(
        envelope_cutoff_frames,
        emphasis_cutoff_frames, emphasis_opacity,
        smooth_attack_coefficient, smooth_release_coefficient
    )

    # Begin processing audio
    jack.activate()

    try:
        while True:
            try:
                jack.process(jack_output, jack_input)
                input_buffer = jack_input[0].tolist()
                for i in xrange(buffer_size):
                    output_buffer[i] = volume_filter.process(input_buffer[i])
            except jack.InputSyncError, e:
                print "JACK: we couldn't process data in time."

            count = map_to_leds(output_buffer[0], map_options) # TODO: respect -f
            send_leds(client, leds, count)
    except KeyboardInterrupt, e:
        pass

    # Close everything
    jack.deactivate()
    jack.detach()
    sock.close()
