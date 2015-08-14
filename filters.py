"""
This module implements the necessary audio filtering that
is applied to samples coming from JACK in order to track
the volume (amplitude) of the audio at any point in time.

Every X samples, led-meter picks a processed sample, and uses
some logic to map it into a number of LEDs.
"""

from math import pi


# Simple filters

class LowPassFilter:
    """
    Simple low-pass filter, single pole.
    """

    @staticmethod
    def get_coefficient(cutoff_frames):
        """
        Calculate the coefficient that needs to be used
        for the filter to have a specific cutoff frequency.
        `cutoff_frames` is the period of that frequency, in frames.
        """
        return 1 / (1 + cutoff_frames / (2 * pi))

    def __init__(self, coefficient):
        """
        Initialize the filter with a coefficient.
        """
        self.coefficient = coefficient
        self.last_output = 0

    def process(self, sample):
        """
        Process a sample with the filter, and return the processed sample.
        """
        a = self.coefficient
        output = a * sample + (1 - a) * self.last_output
        self.last_output = output
        return output

class HighPassFilter:
    """
    Simple high-pass filter, single pole.
    """

    @staticmethod
    def get_coefficient(cutoff_frames):
        """
        Calculate the coefficient that needs to be used
        for the filter to have a specific cutoff frequency.
        `cutoff_frames` is the period of that frequency, in frames.
        """
        return 1 / (1 + (2 * pi) / cutoff_frames)

    def __init__(self, coefficient):
        """
        Initialize the filter with a coefficient.
        """
        self.coefficient = coefficient
        self.last_input = 0
        self.last_output = 0

    def process(self, sample):
        """
        Process a sample with the filter, and return the processed sample.
        """
        output = self.coefficient * (sample + self.last_output - self.last_input)
        self.last_input = sample
        self.last_output = output
        return output

class AttackReleaseFilter:
    """
    Simple attack-release filter. This is pretty much like `LowPassFilter`,
    except that it allows different coefficients to act, depending on wether
    the input is more than the output (attack phase) or less (release phase).
    """

    @staticmethod
    def get_coefficient(frames, point=0.5):
        """
        Calculate the coefficient (attack or release) that needs to be used
        so that the filter needs `frames` frames to transfer a fraction of
        the input to the output. By default that fraction is 0.5, meaning
        half the input has been transferred.
        """
        if frames == 0: return 0.0
        return point ** (1 / float(frames))

    def __init__(self, attack, release):
        """
        Initialize the filter with coefficients for the attack phase
        and the release phase.
        """
        self.attack = attack
        self.release = release
        self.last_output = 0

    def process(self, sample):
        """
        Process a sample with the filter, and return the processed sample.
        """
        a = self.attack if sample > self.last_output else self.release
        output = a * self.last_output + (1 - a) * sample
        self.last_output = output
        return output


# More complex filters

class EnvelopeFollowFilter:
    """
    Envelope follower, based on `AttackReleaseFilter`. It's configured to
    follow the envelope of frequencies higher than the cutoff frequency.
    Lower frequencies are cleaned up from the input before the attack-release
    filter takes place, and high-frequency noise is removed from the envelope
    before returning it to the caller.
    """

    def __init__(self, cutoff_frames, release_point=0.3,
                 high_cutoff_coefficient=1/3.0, high_stages=2,
                 low_cutoff_coefficient=1/1.0, low_stages=1):
        """
        Initialize the filter with a cutoff frequency (`cutoff_frames` is the
        period of that frequency, measured in frames). The release point
        for the attack-release can also be provided. The other parameters are
        used to scale the cutoff frequencies for the low-pass and high-pass
        filters, and their stages (number of times the filter takes place).
        """
        # Initialize the high-pass filter to clean frequencies
        # lower than our specified cutoff frequency.
        coefficient = HighPassFilter.get_coefficient(cutoff_frames / high_cutoff_coefficient)
        self.hp_filters = [HighPassFilter(coefficient) for i in xrange(high_stages)]

        # The attack-release filter must have zero attack time, we're
        # going to follow the envelope. Now, the release: because we're
        # abs()ing the input, there will be at most half the cutoff period
        # between peaks, and in that time we should transfer `release_point`.
        peak_spacing = cutoff_frames / 2
        release = AttackReleaseFilter.get_coefficient(peak_spacing, release_point)
        self.ar_filter = AttackReleaseFilter(attack=0, release=release)

        # Since the time between peaks will be `peak_spacing` or lower,
        # the noise starts at frequency `1 / peak_spacing`. Our low pass
        # filter should remove this, and higher frequencies from the envelope.
        coefficient = LowPassFilter.get_coefficient(peak_spacing / low_cutoff_coefficient)
        self.lp_filters = [LowPassFilter(coefficient) for i in xrange(low_stages)]

    def process(self, sample):
        """
        Process a sample with the filter, and return the processed sample.
        """
        # First, clean the input of low frequencies we can't follow,
        # as well as the DC component.
        cleaned = sample
        for hp_filter in self.hp_filters:
            cleaned = hp_filter.process(cleaned)

        # Get the absolute value of the sample, to make it easier
        # for the attack-release filter to get the envelope.
        cleaned = abs(cleaned)

        # Apply the attack-release filter to get the envelope!
        envelope = self.ar_filter.process(cleaned)

        # Finally, clean the HF noise present in the envelope.
        for lp_filter in self.lp_filters:
            envelope = lp_filter.process(envelope)
        return envelope

class VolumeFollowFilter:
    """
    Follows the average volume of the supplied audio, using
    `EnvelopeFollowFilter`, and can optionally use a high-pass
    filter to emphasize sudden volume changes over smooth ones.

    This is the only filter that is used by led-meter,
    and returns ready-for-display volume.

    FIXME: An envelope follower (alone) is not the right tool for measuring
    volume, since it tracks amplitude rather than power or perceived loudness.
    This can be palliated by using multiple meters, with band-passes each
    covering different sections of the spectrum.
    """

    def __init__(self, envelope_cutoff_frames,
                 emphasis_cutoff_frames, emphasis_opacity,
                 smooth_attack_coefficient, smooth_release_coefficient):
        """
        Initialize the filter with a cutoff frequency for the envelope follower,
        the opacity and cutoff frequency for the high-pass (emphasis) filter,
        and the two coefficients for the final attack-release filter, used
        to smooth the envelope to make it suitable for display.
        """
        # First, build the envelope follower.
        self.envelope_follower = EnvelopeFollowFilter(envelope_cutoff_frames)

        # Then, the high-pass filter for emphasis.
        coefficient = HighPassFilter.get_coefficient(emphasis_cutoff_frames)
        self.emphasis_filter = HighPassFilter(coefficient)
        self.emphasis_opacity = emphasis_opacity

        # And the final attack-release filter.
        self.smooth_filter = AttackReleaseFilter(smooth_attack_coefficient, smooth_release_coefficient)

    def process(self, sample):
        """
        Process a sample with the filter, and return the processed sample.
        """
        # First, get the envelope of the input.
        envelope = self.envelope_follower.process(sample)

        # Now that we have the immediate amplitude, we want to emphasize sudden
        # changes (high frequencies) over constant amplitude (low frequencies),
        # so we partially apply a high-pass filter to the envelope.
        emphasized = self.emphasis_filter.process(envelope)
        opacity = self.emphasis_opacity
        emphasized = opacity * emphasized + (1 - opacity) * envelope

        # Before displaying the emphasized envelope, we want to smooth it
        # but still retain the peaks reached for some time, that's why we
        # apply a final attack-release filter over it.
        smoothed = self.smooth_filter.process(emphasized)
        return smoothed
