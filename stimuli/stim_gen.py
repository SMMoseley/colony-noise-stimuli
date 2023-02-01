# -*- coding: utf-8 -*-
# -*- mode: python -*-
""" Extract songs from the neurobank repository and rescale them """

#The following is based on get-songs.py by cdmeliza
#Praise be his majesty

import os
import numpy as np
import ewave
import nbank
import argparse
import yaml
#import h5py as h5
from pathlib import Path
from core import resample, hp_filter, rescale

# disable locking - neurobank archive is probably on an NFS share
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
__version__ = "20230131"

def get_interval(path, info, interval_ms, dtype):
    with ewave.open(path, "r") as fp:
        rate = fp.sampling_rate
        data = fp.read()
        start, stop, *rest = (int(t * rate / 1000) for t in interval_ms)
        data = data[slice(start, stop)].astype("float32")
        rescaled_data = ewave.rescale(data, dtype)
        return {"signal": rescaled_data,"dBFS":round(info['dBFS'],0),"sampling_rate":rate}

def paddington(song_data, gap=0):    
    note_gap = np.zeros(int(gap*song_data['sampling_rate']), dtype=type(song_data['signal'][0]))
    return np.concatenate((song_data['signal'],note_gap,song_data['signal']))

def make_song(source,name,interval_ms,dataset,args):
    print(f"{source}:")
    path = nbank.get(source, local_only=True)
    info = nbank.describe(source)
    dtype = args.dtype or song_data["signal"].dtype
    print(path, info, interval_ms, dtype)
    song_data = get_interval(path, info['metadata'], interval_ms, dtype)
    print(f" - loaded {dataset}: {song_data['sampling_rate']} Hz sampling rate, {(song_data['signal'].size / song_data['sampling_rate']):.2f} seconds, {song_data['dBFS']:.2f} dBFS")

    song_data['signal'] = paddington(song_data, args.gap)
    print(f" - padded {dataset}: {song_data['signal'].size / song_data['sampling_rate']} seconds,")
    rescale(song_data, args.dBFS)
    absmax = np.amax(np.absolute(song_data["signal"]))
    print(f" - adjusted RMS to {song_data['dBFS']:.2f} dBFS (peak is {absmax:.3f})")

    out_file = name + ".wav"
    Path(out_file).parent.mkdir(exist_ok=True, parents=True)
    with ewave.open(
        out_file, mode="w+", sampling_rate=args.rate, dtype=dtype
    ) as fp:
        fp.write(song_data["signal"])
    print(f" - wrote data to {out_file}")

    if args.deposit:
        metadata = {
            "source_resource": source,
            "source_dataset": dataset,
            "source_interval_ms": interval_ms,
            "dBFS": song_data["dBFS"],
        }
        if args.highpass:
            metadata.update(
                highpass_cutoff=args.highpass,
                highpass_order=args.filter_order,
                highpass_filter="butterworth",
            )
        for res in nbank.deposit(
            args.deposit,
            (out_file.split('/')[-1],),
            dtype="vocalization-wav",
            hash=True,
            auto_id=True,
            **metadata,
        ):
            print(f" - deposited in {args.deposit} as {res['id']}")

def script(argv=None):
    
    p = argparse.ArgumentParser()
    p.add_argument(
        "-v", "--version", action="version", version="%(prog)s " + __version__
    )
    p.add_argument(
        "--rate",
        "-r",
        type=int,
        default=44100,
        help="sampling rate for the output files",
    )
    p.add_argument(
        "--dBFS",
        "-d",
        type=float,
        default=-30,
        help="target level (dBFS) for the output files",
    )
    p.add_argument(
        "--highpass",
        type=float,
        help="cutoff frequency for a highpass butterworth filter to apply between resampling and rescaling",
    )
    p.add_argument(
        "--gap",
        type=float,
        help="add gap in seconds, between the repeating audio",
    )
    p.add_argument(
        "--filter-order",
        type=int,
        default=10,
        help="order for the butterworth highpass filter (default %(default)d)",
    )
    p.add_argument(
        "--dtype",
        type=type,
        default=np.int16,
        help="specify data type of the output sound file",
    )
    p.add_argument(
        "--deposit",
        help="deposit files in neurobank archive (requires write access to registry)",
    )
    p.add_argument("songs", help="YAML file with songs to extract")
    args = p.parse_args(argv)
    with open(args.songs) as fp:
        songs = yaml.safe_load(fp)

    dataset = songs['params']['dataset']
    interval_ms = songs['params']['interval_ms']

    for song in songs['clean_stim']['name']:
        source = song
        name = "clean_stim/" + song + "_x2"
        make_song(source, name, interval_ms, dataset, args)
        
    fg_dbfs = songs['snr_stim']['fg_dbfs']
    for f in songs['snr_stim']['foregrounds']:
        for b in songs['snr_stim']['backgrounds']:
            for d in songs['snr_stim']['bg_dbfs']:
                source = f+str(fg_dbfs)+'_'+b+str(d)
                name = "snr_stim/" + source + "_x2"
                make_song(source, name, interval_ms, dataset, args)

if __name__ == "__main__":
    script()
