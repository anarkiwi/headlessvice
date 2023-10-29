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

with tempfile.TemporaryDirectory() as tmpdir:
    fifoname = os.path.join(tmpdir, "fifo")
    os.mkfifo(fifoname)
    cli = ["/usr/local/bin/vsid", "-sounddev", "dump", "-soundarg", fifoname] + vsidargs

    with open(dumpname, "wb") as dump:
        cctx = zstandard.ZstdCompressor()
        with cctx.stream_writer(dump) as writer:
            fifofh = os.open(fifoname, os.O_RDONLY | os.O_NONBLOCK)
            with Popen(cli, stdout=PIPE, stderr=STDOUT, shell=False) as viceproc:
                procdata = psutil.Process(viceproc.pid)
                buffer = ""
                while True:
                    try:
                        data = os.read(fifofh, 1024).decode("utf8")
                    except BlockingIOError:
                        time.sleep(0.001)
                        continue
                    if len(data) == 0 and procdata.status() == psutil.STATUS_ZOMBIE:
                        break
                    buffer += data
                    while True:
                        npos = buffer.find("\n")
                        if npos == -1:
                            break
                        line = buffer[:npos]
                        buffer = buffer[npos + 1 :]
                        if ":" in line:
                            continue
                        clock, addr, val = [int(i) for i in line.split()]
                        chipno = int(addr / 32)
                        chipbase = chipno * 32
                        addr -= chipbase
                        line = " ".join([str(i) for i in [clock, chipno, addr, val]]) + "\n"
                        writer.write(line.encode("utf8"))
