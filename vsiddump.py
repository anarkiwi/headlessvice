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

# compress repeated writes, add chipno
class reg_processor:
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
                            process_data(buffer[:last_newline])
                            buffer = buffer[last_newline + 1 :]
                writer.write(process_data(buffer))


if __name__ == "__main__":
    main()
