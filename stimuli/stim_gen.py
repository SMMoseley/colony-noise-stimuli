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
import h5py as h5
from core import resample, hp_filter, rescale

# disable locking - neurobank archive is probably on an NFS share
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

__version__ = "20210215"


def get_interval(path, info):
    with ewave.open(path, "r") as fp:
        data = fp.read()
        #sampling_rate = dset.attrs["sampling_rate"]
        #start, stop, *rest = (int(t * sampling_rate / 1000) for t in interval_ms)
        #data = dset[slice(start, stop)].astype("float32")
        return {"signal": data,"dBFS":round(info['dBFS'],0)}

def double_down(signal):
    
    return np.concatenate((signal,signal))
    
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
        "--filter-order",
        type=int,
        default=10,
        help="order for the butterworth highpass filter (default %(default)d)",
    )
    p.add_argument(
        "--dtype",
        help="specify data type of the output sound file (defaults to the data type in the arf file",
    )
    p.add_argument(
        "--deposit",
        help="deposit files in neurobank archive (requires write access to registry)",
    )
    p.add_argument("songs", help="YAML file with songs to extract")
    args = p.parse_args(argv)
    with open(args.songs) as fp:
        songs = yaml.safe_load(fp)

    for song in songs:
        print(f"{song['source']}:")
        path = nbank.get(song["source"], local_only=True)
        info = nbank.describe(song["source"])
        song_data = get_interval(path, info['metadata'])
        print(
            f" - loaded {song['dataset']}: {song_data['signal'].size} samples, RMS {song_data['dBFS']:.2f} dBFS"
        )
        
        song_data['signal'] = double_down(song_data['signal'])
        print(
            f" - doudbled {song['dataset']}: {song_data['signal'].size} samples"
        )
        
        rescale(song_data, args.dBFS)
        absmax = np.amax(np.absolute(song_data["signal"]))
        print(f" - adjusted RMS to {song_data['dBFS']:.2f} dBFS (peak is {absmax:.3f})")

        out_file = song["name"] + ".wav"
        dtype = args.dtype or song_data["signal"].dtype
        with ewave.open(
            out_file, mode="w", sampling_rate=args.rate, dtype=dtype
        ) as fp:
            fp.write(song_data["signal"])
        print(f" - wrote data to {out_file}")

        if args.deposit:
            metadata = {
                "source_resource": song["source"],
                "source_dataset": song["dataset"],
                "source_interval_ms": song["interval_ms"],
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
                (out_file,),
                dtype="vocalization-wav",
                hash=True,
                auto_id=True,
                **metadata,
            ):
                print(f" - deposited in {args.deposit} as {res['id']}")


if __name__ == "__main__":
    script()
