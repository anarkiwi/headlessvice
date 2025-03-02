#!/usr/bin/env python3

import argparse
import tempfile
import time
import os
from subprocess import Popen, PIPE, STDOUT
import psutil
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
            try:
                clock_diff, irq_diff, nmi_diff, chipno, addr, val = [
                    int(i) for i in line.split()
                ]
            except ValueError:
                continue
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


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, prefix_chars="-+")
    parser.add_argument("--dump", dest="dump")
    args, vsidargs = parser.parse_known_args()
    processor = reg_processor()

    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = os.path.join(tmpdir, "fifo")
        os.mkfifo(fifoname)
        cli = [
            "/usr/local/bin/vsid",
            "-silent",
            "-sounddev",
            "dump",
            "-soundarg",
            fifoname,
        ] + vsidargs

        with open(args.dump, "wb") as dump:
            cctx = zstandard.ZstdCompressor()
            with cctx.stream_writer(dump) as writer:
                fifofh = os.open(fifoname, os.O_RDONLY | os.O_NONBLOCK)
                buffer = ""
                with Popen(cli, stdout=PIPE, stderr=STDOUT, shell=False) as viceproc:
                    procdata = psutil.Process(viceproc.pid)
                    last_data = 0
                    while True:
                        try:
                            data = os.read(fifofh, int(1e6)).decode("utf8")
                            buffer += data
                        except BlockingIOError:
                            time.sleep(0.001)
                            continue
                        now = time.time()
                        if len(data) == 0:
                            if (
                                now - last_data > 1
                                and procdata.status() == psutil.STATUS_ZOMBIE
                            ):
                                break
                        else:
                            last_data = now
                        last_newline = buffer.rfind("\n")
                        if last_newline != -1:
                            writer.write(processor.process(buffer[:last_newline]))
                            buffer = buffer[last_newline + 1 :]
                writer.write(processor.process(buffer))
        if processor.lines_out:
            print(
                args.dump,
                "in",
                processor.lines_in,
                "out",
                processor.lines_out,
                processor.lines_out / processor.lines_in * 100,
                "%",
            )


if __name__ == "__main__":
    main()
