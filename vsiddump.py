#!/usr/bin/python3

import sys
import tempfile
import time
import os
from subprocess import Popen, PIPE, STDOUT
import psutil
import zstandard

timeout = 10
dumpname = sys.argv[1]
vsidargs = sys.argv[2:]


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
        self.lastclock = 0
        self.sidstate = {}

    def process(self, data):
        lines = []
        for line in data.splitlines():
            if ":" in line:
                continue
            clock_diff, addr, val = [int(i) for i in line.split()]
            chipno = int(addr / 32)
            chipbase = chipno * 32
            addr -= chipbase
            linestate = (chipno, addr)
            self.clock += clock_diff
            mask = self.regwidths.get(addr, 255)
            val = val & mask
            if self.sidstate.get(linestate, None) == val:
                continue
            self.sidstate[linestate] = val
            lines.append(
                " ".join(
                    [str(i) for i in [self.clock - self.lastclock, chipno, addr, val]]
                )
                + "\n"
            )
            lastclock = self.clock
        return "".join(lines).encode("utf8")


def main():
    processor = reg_processor()

    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = os.path.join(tmpdir, "fifo")
        os.mkfifo(fifoname)
        cli = [
            "/usr/local/bin/vsid",
            "-sounddev",
            "dump",
            "-soundarg",
            fifoname,
        ] + vsidargs

        with open(dumpname, "wb") as dump:
            cctx = zstandard.ZstdCompressor()
            with cctx.stream_writer(dump) as writer:
                fifofh = os.open(fifoname, os.O_RDONLY | os.O_NONBLOCK)
                buffer = ""
                with Popen(cli, stdout=PIPE, stderr=STDOUT, shell=False) as viceproc:
                    procdata = psutil.Process(viceproc.pid)
                    while True:
                        try:
                            data = os.read(fifofh, 1024).decode("utf8")
                            buffer += data
                        except BlockingIOError:
                            time.sleep(0.001)
                            continue
                        if len(data) == 0 and procdata.status() == psutil.STATUS_ZOMBIE:
                            break
                        last_newline = buffer.rfind("\n")
                        if last_newline != -1:
                            writer.write(processor.process(buffer[:last_newline]))
                            buffer = buffer[last_newline + 1 :]
                writer.write(processor.process(buffer))


if __name__ == "__main__":
    main()
