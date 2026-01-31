#!/usr/bin/env python3

import argparse
import hashlib
import os
import multiprocessing
import subprocess
import tempfile
import pandas as pd


MAX_REG = 24
PDTYPE = pd.UInt32Dtype()


def squeeze_changes(orig_df):
    diff_cols = orig_df.reg.unique()
    dfs = []
    for _c, df in orig_df.groupby("chipno"):
        reg_df = df.pivot(columns="reg", values="val").astype(PDTYPE).ffill().fillna(0)
        reg_df = reg_df.loc[
            (reg_df[diff_cols].shift(fill_value=0) != reg_df[diff_cols]).any(axis=1)
        ]
        df = reg_df.join(df)[orig_df.columns]
        dfs.append(df)
    df = pd.concat(dfs).sort_values("clock").reset_index(drop=True)
    return df


def reduce_res(orig_df):
    df = orig_df.copy()
    for reg, mask in (
        (3, 2**4 - 1),  # v1 PWM high
        (10, 2**4 - 1),  # v2 PWM high
        (17, 2**4 - 1),  # v3 PWM high,
        (21, 2**3 - 1),  # filter cutoff low
        (23, (2**8 - 1) - 2**3),  # clear filter external
    ):
        m = df["reg"] == reg
        df.loc[m, "val"] = df[m]["val"] & mask
    return df


def dumptune(dumpdir, args, vsidargs, tune=None):
    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = os.path.join(tmpdir, "fifo")
        os.mkfifo(fifoname)
        cli = (
            [
                "/usr/local/bin/vsid",
                "-console",
                "-logfile",
                "/dev/null",
                "+logtofile",
                "+logtostdout",
                "-debug",
                "-warp",
                "-sound",
                "-soundwarpmode",
                str(1),
                "-sounddev",
                "dump",
                "-soundarg",
                fifoname,
            ]
            + vsidargs
            + [args.sid]
        )
        base = os.path.basename(args.sid).split(".")[0]
        if base is not None:
            base = ".".join((base, str(tune)))
        base = ".".join((base, "dump.parquet"))
        dumpname = os.path.join(dumpdir, base)

        def run_processor():
            try:
                with open(fifoname, "r", encoding="utf8") as f:
                    df = pd.read_csv(
                        f,
                        header=None,
                        delim_whitespace=True,
                        names=[
                            "clock_diff",
                            "irq_diff",
                            "nmi_diff",
                            "chipno",
                            "reg",
                            "val",
                        ],
                    )
                df["clock"] = df["clock_diff"].cumsum()
                df["irq"] = (df["clock"] - df["irq_diff"]).clip(lower=0)
                df = df[df["reg"] <= MAX_REG]
                df = df[["clock", "irq", "chipno", "reg", "val"]]
                df = reduce_res(df)
                df = squeeze_changes(df)
                print(df["irq"].min(), df["irq"].max())
                df = df.astype(
                    {
                        "clock": PDTYPE,
                        "irq": PDTYPE,
                        "chipno": pd.UInt8Dtype(),
                        "reg": pd.UInt8Dtype(),
                        "val": pd.UInt8Dtype(),
                    }
                )
                df.to_parquet(dumpname, compression="zstd")
            except Exception as err:
                print("run_processor() failed:", err)

        processor = multiprocessing.Process(target=run_processor)
        with subprocess.Popen(
            cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ) as vice:
            processor.start()
            vice.communicate()
        processor.join()


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, prefix_chars="-+")
    parser.add_argument("--dumpdir", dest="dumpdir")
    parser.add_argument("--sid", dest="sid")
    parser.add_argument("--songlengths", dest="songlengths", default=None)
    parser.add_argument("--ntsc", action=argparse.BooleanOptionalAction, default=False)
    args, vsidargs = parser.parse_known_args()
    dumpdir = args.dumpdir
    if not args.sid:
        raise ValueError("need --sid")

    if not dumpdir:
        dumpdir = os.path.dirname(args.sid)

    if args.songlengths is None:
        dumptune(dumpdir, args, vsidargs)
        return

    with open(args.sid, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest().lower()
    songlengths = None
    with open(args.songlengths, "r", encoding="utf8") as f:
        for line in f:
            if line.startswith(md5):
                songlengths = line
                break
    if songlengths is None:
        raise ValueError("no songlengths for %s" % args.sid)

    sid_phi = 985248
    if args.ntsc:
        sid_phi = 1022727

    songlengths = songlengths.strip().split("=")[1].split(" ")
    if not songlengths:
        raise ValueError("no songlengths for %s" % args.sid)

    os.makedirs("/root/.local/state/vice/", exist_ok=True)
    for tune, songlength in enumerate(songlengths, start=1):
        seconds = 0
        try:
            base, ms = songlength.split(".")
            seconds = float(ms) / 1e3
        except ValueError:
            base = songlength
        base = [int(i) for i in base.split(":")]
        if len(base) == 1:
            seconds += base[0]
        elif len(base) == 2:
            seconds += base[0] * 60 + base[1]
        else:
            raise ValueError("cannot parse songlength %s" % songlength)
        limit = int(sid_phi * seconds)
        print(tune, songlength, seconds, limit)
        dumptune(
            dumpdir,
            args,
            vsidargs + ["-tune", str(tune), "-limitcycles", str(limit)],
            tune,
        )


if __name__ == "__main__":
    main()
