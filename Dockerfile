# Containerized, headless VICE, suitable for ripping SID register dumps, etc.
#
# $ docker build -f Dockerfile . -t anarkiwi/headlessvice
#
# One SID:
#
# $ docker run --rm -v /scratch/hvsc:/scratch/hvsc -t anarkiwi/headlessvice /usr/local/bin/vsiddump.py --dumpdir=/scratch/hvsc/ --songlengths=/scratch/hvsc/C64Music/DOCUMENTS/Songlengths.md5 --sid /scratch/hvsc/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid
#
# Multiple directories:
#
# $ for d in /scratch/hvsc/C64Music/MUSICIANS/G/Goto80 /scratch/hvsc/C64Music/MUSICIANS/0-9/4-Mat /scratch/hvsc/C64Music/MUSICIANS/H/Hubbard_Rob ; do ddir=$(basename $d) ; mkdir /scratch/preframr/dumps/$ddir ; find $d -name \*sid -print |parallel --jobs 64 --progress docker run --rm -v /scratch/hvsc:/scratch/hvsc -v /scratch/preframr/dumps:/scratch/preframr/dumps -t anarkiwi/headlessvice /usr/local/bin/vsiddump.py --dumpdir=/scratch/preframr/dumps/$ddir --songlengths=/scratch/hvsc/C64Music/DOCUMENTS/Songlengths.md5 --sid ; done
#
# Entire HVSC:
#
# find /scratch/hvsc -name \*sid -print |parallel --jobs 8 --progress docker run --rm -v /scratch/hvsc:/scratch/hvsc -t anarkiwi/headlessvice /usr/local/bin/vsiddump.py --songlengths=/scratch/hvsc/C64Music/DOCUMENTS/Songlengths.md5 --sid

FROM ubuntu:latest AS builder

RUN apt-get update && apt-get install -y git
RUN apt-get update && apt-get install -y file make autoconf gcc g++ flex bison dos2unix xa65 libcurl4-openssl-dev pkg-config zlib1g-dev python3-pytest python3-zstandard python3-psutil

WORKDIR /vice
RUN git clone --recursive https://github.com/anarkiwi/asid-vice

# We need asid-vice for multi SID support.
# asid-vice carries the VICE log_file_close() use-after-free fix (via revice
# patch 07) since anarkiwi/asid-vice#38, so no patching is needed here.
WORKDIR /vice/asid-vice
# Ensure the revice submodule (which carries the bustrace sources referenced by
# the wired Makefile.am) is fully populated, and force regeneration of
# src/c64/Makefile.in.
#
# asid-vice master has the bustrace BUILD wiring in src/c64/Makefile.am
# (anarkiwi/asid-vice#39) but ships a committed, PRE-GENERATED
# src/c64/Makefile.in that predates it (0 soundbustrace refs). A fresh git
# checkout gives Makefile.am and Makefile.in equal mtimes, so the automake run
# below sees Makefile.in as up to date and does NOT regenerate it -> the bustrace
# sources (src/revice/.../soundbustrace.c) are silently dropped from the build
# and vsid links WITHOUT the `-bustrace` option (the cmdline parser then rejects
# it with exit 255). Bumping Makefile.am's mtime forces automake to regenerate
# Makefile.in from source. We touch ONLY src/c64/Makefile.am: do not run
# apply-wiring.sh or touch src/monitor/Makefile.am here -- on the already-wired
# master that perturbs the monitor lexer/parser build and breaks
# `make -C src/monitor`. Verify the fix with:
#   nm /usr/local/bin/vsid | grep -c bustrace   (expect >0)
RUN git submodule update --init --recursive && \
    touch src/c64/Makefile.am
# --enable-cpuhistory is REQUIRED for the bustrace feature: the per-access hook
# in src/c64/vsidcpu.c that feeds revice_bustrace lives inside
# #ifdef FEATURE_CPUMEMHISTORY, which this flag turns on. asid-vice master
# already carries the bustrace wiring (anarkiwi/asid-vice#39); cpuhistory is the
# only build change needed. It must NOT alter the SID register dump (verified
# byte-identical against the pre-cpuhistory build).
RUN aclocal && autoheader && autoconf && automake --force-missing --add-missing && ./autogen.sh && \
    ./configure --enable-headlessui --enable-cpuhistory --disable-pdf-docs --without-pulse --without-alsa --without-png --disable-dependency-tracking --disable-realdevice --disable-rs232 --disable-ipv6 --disable-native-gtk3ui --disable-sdlui --disable-sdlui2 --disable-ffmpeg
RUN make -C src/monitor mon_parse.h mon_parse.c mon_lex.c && \
    make -j"$(nproc)" all && make install

FROM ubuntu:latest
RUN apt-get update && apt-get install -yq libcurl4 libgomp1 zlib1g python3 python3-pip python3-psutil python3-pandas python3-pytest && apt -y autoremove && apt-get clean && pip install --break-system-packages pyarrow
COPY --from=builder /usr/local /usr/local
COPY vsiddump.py /usr/local/bin/vsiddump.py
COPY test_vsiddump.py /usr/local/bin/test_vsiddump.py

RUN cd /usr/local/bin && python3 -m pytest test_vsiddump.py -v && rm test_vsiddump.py
RUN /usr/local/bin/vsid -h -console -silent
RUN /usr/local/bin/vsiddump.py --dump /tmp/test.zst --help
