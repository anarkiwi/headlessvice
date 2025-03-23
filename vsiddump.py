#!/usr/bin/env python3

import argparse
import hashlib
import os
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
import zstandard


# compress repeated writes, mask unused bits, add chipno
class reg_processor:
    regwidths = {
        3: 2**4 - 1,  # v1 PWM high
        10: 2**4 - 1,  # v2 PWM high
        17: 2**4 - 1,  # v3 PWM high,
        21: 2**3 - 1,  # filter cutoff low
        23: (2**8 - 1) - 2**3,  # clear filter external
    }

    def __init__(self):
        self.clock = 0
        self.sidstate = {}
        self.lines_in = 0
        self.lines_out = 0

    def process(self, data):
        lines = []
        for line in data.splitlines():
            clock_diff, irq_diff, nmi_diff, chipno, addr, val = [
                int(i) for i in line.split()
            ]
            self.lines_in += 1
            linestate = (chipno, addr)
            self.clock += clock_diff
            mask = self.regwidths.get(addr, 255)
            val = val & mask
            if self.sidstate.get(linestate, None) == val:
                continue
            self.lines_out += 1
            self.sidstate[linestate] = val
            lines.append(
                " ".join(
                    [
                        str(i)
                        for i in [
                            self.clock,
                            irq_diff,
                            nmi_diff,
                            chipno,
                            addr,
                            val,
                        ]
                    ]
                )
                + "\n"
            )
        return "".join(lines).encode("utf8")


def dumptune(args, vsidargs, tune=None):
    processor = reg_processor()

    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = os.path.join(tmpdir, "fifo")
        os.mkfifo(fifoname)
        cli = (
            [
                "/usr/local/bin/vsid",
                "-console",
                "+logtofile",
                "-logtostdout",
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
        base = ".".join((base, "dump.zst"))
        dumpname = os.path.join(args.dumpdir, base)

        with open(dumpname, "wb") as dump:
            cctx = zstandard.ZstdCompressor()
            with cctx.stream_writer(dump) as writer:
                with ProcessPoolExecutor(max_workers=1) as pool:
                    _result = pool.submit(subprocess.check_call, cli)
                    with open(fifoname, "r", encoding="utf8") as f:
                        for line in f:
                            writer.write(processor.process(line))
        if processor.lines_out:
            print(
                dumpname,
                "in",
                processor.lines_in,
                "out",
                processor.lines_out,
                processor.lines_out / processor.lines_in * 100,
                "%",
            )


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, prefix_chars="-+")
    parser.add_argument("--dumpdir", dest="dumpdir")
    parser.add_argument("--sid", dest="sid")
    parser.add_argument("--songlengths", dest="songlengths", default=None)
    parser.add_argument("--ntsc", action=argparse.BooleanOptionalAction, default=False)
    args, vsidargs = parser.parse_known_args()
    if not (args.dumpdir and args.sid):
        raise ValueError("need --dumpdir and --sid")

    if args.songlengths is None:
        dumptune(args, vsidargs)
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
        dumptune(
            args, vsidargs + ["-tune", str(tune), "-limitcycles", str(limit * 10)], tune
        )


if __name__ == "__main__":
    main()
