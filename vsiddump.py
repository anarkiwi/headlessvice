#!/usr/bin/python3

import sys
import tempfile
import os
from subprocess import Popen, PIPE
import zstandard

dumpname = sys.argv[1]
vsidargs = sys.argv[2:]

with tempfile.TemporaryDirectory() as tmpdir:
    fifoname = os.path.join(tmpdir, "fifo")
    os.mkfifo(fifoname)
    cli = ["/usr/local/bin/vsid", "-sounddev", "dump", "-soundarg", fifoname] + vsidargs

    with open(dumpname, "wb") as dump:
        cctx = zstandard.ZstdCompressor()
        with cctx.stream_writer(dump) as writer:
            viceproc = Popen(cli, stdout=PIPE, stderr=PIPE, shell=False)
            os.set_blocking(viceproc.stdout.fileno(), False)

            with open(fifoname, "r") as fifo:
                while True:
                    viceproc.stdout.read(0)
                    line = fifo.readline()
                    if not line:
                        break
                    if ":" in line:
                        continue
                    clock, addr, val = [int(i) for i in line.split()]
                    chipno = int(addr / 32)
                    chipbase = chipno * 32
                    addr -= chipbase
                    line = " ".join([str(i) for i in [clock, chipno, addr, val]]) + "\n"
                    writer.write(line.encode("utf8"))

    viceproc.terminate()
