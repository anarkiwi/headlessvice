#!/usr/bin/env python3

import multiprocessing
import os
import pickle
import tempfile

import pandas as pd
import pytest

import vsiddump


# Columns vsid emits to the fifo, space separated, no header:
# clock_diff irq_diff nmi_diff chipno reg val
SAMPLE_DUMP = """\
0 0 0 0 0 16
10 0 0 0 1 32
10 0 0 0 1 32
10 0 0 0 4 17
10 0 0 0 25 255
10 0 0 0 1 48
"""


def write_dump(tmpdir, contents=SAMPLE_DUMP):
    path = os.path.join(tmpdir, "dump")
    with open(path, "w", encoding="utf8") as f:
        f.write(contents)
    return path


def test_run_processor_is_picklable():
    # On Python 3.14 the default multiprocessing start method on Linux is
    # forkserver, which pickles the target. A local closure would fail here.
    pickle.loads(pickle.dumps(vsiddump.run_processor))


def test_process_dump_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        df = vsiddump.process_dump(write_dump(tmpdir))
    assert list(df.columns) == ["clock", "irq", "chipno", "reg", "val"]
    # reg 25 is > MAX_REG (24) and must be dropped.
    assert df["reg"].max() <= vsiddump.MAX_REG
    # clock is the cumulative sum of clock_diff.
    assert df["clock"].is_monotonic_increasing
    # Duplicate reg=1 val=32 write is squeezed out (no change).
    reg1 = df[df["reg"] == 1]["val"].tolist()
    assert reg1 == [32, 48]


def test_process_dump_dtypes():
    with tempfile.TemporaryDirectory() as tmpdir:
        df = vsiddump.process_dump(write_dump(tmpdir))
    assert df["clock"].dtype == vsiddump.PDTYPE
    assert df["irq"].dtype == vsiddump.PDTYPE
    assert df["chipno"].dtype == pd.UInt8Dtype()
    assert df["reg"].dtype == pd.UInt8Dtype()
    assert df["val"].dtype == pd.UInt8Dtype()


def test_run_processor_writes_parquet():
    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = write_dump(tmpdir)
        dumpname = os.path.join(tmpdir, "out.dump.parquet")
        vsiddump.run_processor(fifoname, dumpname)
        assert os.path.exists(dumpname)
        df = pd.read_parquet(dumpname)
    assert list(df.columns) == ["clock", "irq", "chipno", "reg", "val"]


def test_run_processor_in_subprocess():
    # Exercises the same path that failed in the bug report: launching a
    # multiprocessing.Process with run_processor as the target.
    with tempfile.TemporaryDirectory() as tmpdir:
        fifoname = write_dump(tmpdir)
        dumpname = os.path.join(tmpdir, "out.dump.parquet")
        ctx = multiprocessing.get_context("forkserver")
        proc = ctx.Process(target=vsiddump.run_processor, args=(fifoname, dumpname))
        proc.start()
        proc.join()
        assert proc.exitcode == 0
        assert os.path.exists(dumpname)


def test_reduce_res_masks_registers():
    df = pd.DataFrame(
        {
            "clock": [0, 1, 2],
            "irq": [0, 0, 0],
            "chipno": [0, 0, 0],
            "reg": [3, 21, 23],
            "val": [0xFF, 0xFF, 0xFF],
        }
    )
    out = vsiddump.reduce_res(df)
    assert out[out["reg"] == 3]["val"].iloc[0] == 0x0F  # PWM high nibble
    assert out[out["reg"] == 21]["val"].iloc[0] == 0x07  # filter cutoff low 3 bits
    assert out[out["reg"] == 23]["val"].iloc[0] == 0xF7  # filter external cleared


class _Args:
    def __init__(self, sid, bustrace):
        self.sid = sid
        self.bustrace = bustrace


def _capture_cli(monkeypatch, bustrace):
    """Run dumptune with vsid/processor stubbed out and capture the vsid CLI."""
    captured = {}

    class _FakePopen:
        def __init__(self, cli, **kwargs):
            captured["cli"] = cli

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def communicate(self):
            return (b"", b"")

    class _FakeProc:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr(vsiddump.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(vsiddump.multiprocessing, "Process", _FakeProc)
    with tempfile.TemporaryDirectory() as dumpdir:
        vsiddump.dumptune(
            dumpdir, _Args("/x/Tune.sid", bustrace), ["-tune", "1"], tune=1
        )
    return captured["cli"]


def test_dumptune_no_bustrace_omits_flag(monkeypatch):
    cli = _capture_cli(monkeypatch, bustrace=False)
    assert "-bustrace" not in cli
    # The register-dump path is unchanged.
    assert "-sounddev" in cli and "dump" in cli


def test_dumptune_bustrace_adds_flag(monkeypatch):
    cli = _capture_cli(monkeypatch, bustrace=True)
    assert "-bustrace" in cli
    busarg = cli[cli.index("-bustrace") + 1]
    # Writes to a hidden temp file named for the .bus.bin (atomic-rename target).
    assert os.path.basename(busarg) == ".Tune.1.bus.bin"
    # The dump driver is still wired exactly as before (bustrace is additive).
    assert "-sounddev" in cli and "dump" in cli


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
