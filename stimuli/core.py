# -*- coding: utf-8 -*-
# -*- mode: python -*-
import ewave
import nbank
import logging

log = logging.getLogger("colony-noise")  # root logger


def setup_log(log, debug=False):
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    loglevel = logging.DEBUG if debug else logging.INFO
    log.setLevel(loglevel)
    ch.setLevel(loglevel)
    ch.setFormatter(formatter)
    log.addHandler(ch)


def load_wave(file):
    path = nbank.get(file, local_only=True)
    if path is None:
        path = file
    with ewave.open(path, "r") as fp:
        if fp.nchannels != 1:
            raise ValueError(f"{file} has more than one channel")
        data = ewave.rescale(fp.read(), "float32")
        ampl = dBFS(data)
        return {
            "name": file,
            "signal": data,
            "sampling_rate": fp.sampling_rate,
            "duration": fp.nframes / fp.sampling_rate,
            "dBFS": ampl,
        }


def dBFS(signal):
    """ Returns the RMS level of signal, in dB FS"""
    import numpy as np
    rms = np.sqrt(np.mean(signal * signal))
    return 20*np.log10(rms) + 3.0103


def peak(signal):
    """ Returns the peak level of signal, in dB FS"""
    import numpy as np
    absmax = np.amax(np.absolute(signal))
    return 20*np.log10(absmax)


def resample(song, target):
    """ Resample the data in a song to target rate (in Hz)"""
    import samplerate
    if song["sampling_rate"] == target:
        return song
    ratio = 1.0 * target / song["sampling_rate"]
    # NB: this silently converts data to float32
    data = samplerate.resample(song["signal"], ratio, "sinc_best")
    song.update(signal=data, sampling_rate=target, dBFS=dBFS(data))


def hp_filter(song, cutoff, order=12):
    """ Highpass filter the song to remove DC and low-frequency noise """
    import scipy.signal as sg
    sos = sg.butter(order, cutoff, fs=song["sampling_rate"], btype="highpass", output="sos")
    filtered = sg.sosfilt(sos, song["signal"])
    song.update(signal=filtered, dBFS=dBFS(filtered))


def rescale(song, target):
    """ Rescale the data in a song to a target dBFS """
    data = song["signal"]
    scale = 10 ** ((target - song["dBFS"]) / 20)
    song.update(signal=data * scale)
    song.update(dBFS=dBFS(song["signal"]))


def ramp_signal(song, ramp=0.002):
    """ Apply a squared cosine ramp to a signal. """
    from numpy import linspace, pi, sin, cos
    s = song["signal"]
    n = int(ramp * song["sampling_rate"])
    t = linspace(0, pi/2, n)
    s[:n] *= sin(t)**2
    s[-n:] *= cos(t)**2


def all_same(seq):
    """Returns true iff all the elements of seq are the same"""
    it = iter(seq)
    first = next(it)
    for e in it:
        if e != first:
            return False
    return True