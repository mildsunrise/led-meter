# led-meter

This is a little program I wrote, that controls a set of LEDs
to track the volume of real-time audio it gets from JACK.

You can see this in action (two instances of this program controlling
the LEDs of two NanoBridge M5) [here][demo]. This is able to control
up to 32 LEDs, but is optimized to work with few LEDs (in the demo,
the meters have just four LEDs).

It has two parts:

 - The **server** runs on the device having the LEDs.  
   It listens for UDP packets that tell it what LEDs to turn on / off.  
   Thus, the server is device-specific, see below.

 - The **client** runs on your computer, grabs audio from JACK,
   processes it and send commands to the server to update the LEDs.

## Usage

First grab, compile and run an appropiate server on your device.  
These are the current server implementations:

 - `sysfs-leds`: Controls LEDs exposed through the standard sysfs interface
   (indicated for devices running OpenWRT or a modern Linux).  
   To see if that is your case, look at `/sys/class/leds`. If there are
   folders, try writing `0` and `255` to the `brightness` file inside each
   of them, and see if some LEDs turn on / off.
 - `airos`: Controls LEDs exposed through AirOS-specific files.  
   There is a precompiled server (`servers/airos`), just copy it to
   your AirOS-powered device and run it.
 - If none of the above suit you, you'll have to write your own server
   (see the format of the packets below).

Once you have located a server that suits you, compile and run it in the
device. Then to make sure everything works, try playing with `ledp.py`, i.e.:

    # Turns all controllable LEDs on
    ./ledp.py <IP of server> 11111111111111111111111111111111
    # Turns all controllable LEDs off
    ./ledp.py <IP of server> 00000000000000000000000000000000
    # Turns on LED 0 only
    ./ledp.py <IP of server> 1-------------------------------
    # Turns on LED 5 only
    ./ledp.py <IP of server> -----1--------------------------

The next step is to locate the IDs of the LEDs that will be used for the
volume meter, and write them down *in order* (LED representing lowest volume
first).

Now run led-meter:

    pip install docopt jack
    ./led-meter.py <comma-separated list of LEDs> <IP of server>

Where the first argument is something like `1,8,6,11`. The more LEDs that are
in the list, the most accurate your meter will be, but again, this can produce
acceptable results even with three LEDs (see next section).

That's it! Just connect your favorite player to the led-meter:input port,
and you should see the LEDs change.

## Customizing metering

There are four important parameters you want to tweak, especially if your
device has very few LEDs or a lot of LEDs.

 - `-k` is a number between `0` and `1`. If you set it to zero, the
   meter will show the actual DB volume. But if you set it to one,
   the *changes* in volume will be displayed instead. By default it's set
   to `0.72`, which is a balance between both.

 - `-s` is the DB volume that causes no LEDs to be active.  
   `-e` is the DB volume that causes all LEDs to be active.  
   This two options let you specify the volume range covered by your meter.

 - `-r` is the release time. It's the time, in milliseconds, that takes for
   the volume level to "go down". If you set it high, the meter will keep
   the volume peaks for a while before the LEDs start to turn off, if you
   set it low, the meter will update instantly.

If you have very few LEDs, and you want to see more action (you want your
meter to mark the beats and notes rather than some constant volume) set
`-k` higher. On the other hand, if you have lots of LEDs, you may want to
tweak `-s` and `-e` to cover a greater range, and set `-k` to zero.

How you set `-r` is more of a personal preference. Try experimenting with
many values. It's not recommended to set `-r` below 40, though.

**Protip:** Nothing stops you from having many meters, measuring different
parts of the frequency spectrum, as I did in the demo.

## The LEDP protocol

The protocol is very simple. The server listens on port 5021 by default.
The client simply sends UDP datagrams with the following format:

    Bytes 0:  protocol version
    Bytes 1,2,3,4:  mask (network endianness)
    Bytes 5,6,7,8:  values (network endianness)

The protocol version is expected to be 1.

Where `mask` is a bitmask, with each bit specifying whether the LED at that
position should have its on/off status set (1), or should be left untouched (0).

`values` is another bitmask. For LEDs that have their mask bit set to 1, their
bit in the `values` bitmask determines whether it should be turned on (1) or
off (0).

For LEDs that have their mask bit set to 0, their bit in the `values` bitmask
is ignored.



[demo]: https://twitter.com/mild_sunrise/status/628315996315611137
