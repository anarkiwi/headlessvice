# Containerized, headless VICE, suitable for ripping SID register dumps, etc.
#
# Example usage:
#
# $ docker build -f Dockerfile . -t anarkiwi/headlessvice
# $ mkdir vice
# $ cp /somewhere/paradroid.sid ~/vice
# $ docker run --rm -v ~/vice:/vice -ti anarkiwi/headlessvice vsid -verbose -sounddev dump -soundarg /vice/paradroid.dump -warp -limit 10000000 /vice/paradroid.sid
#
# $ SIDS=/sids ; cd $SIDS && find . -type f -name \*sid|parallel docker run --rm -v $SIDS:/vice -i anarkiwi/headlessvice vsid -sounddev dump -soundarg /vice/`basename {}`.dump -warp -limit 900000000 /vice/{}

FROM ubuntu:latest AS builder

RUN apt-get update && apt-get install -y git
RUN apt-get update && apt-get install -y file make autoconf gcc g++ flex bison dos2unix xa65 libcurl4-openssl-dev pkg-config zlib1g-dev python3-pytest python3-zstandard python3-psutil

WORKDIR /vice
RUN git clone https://github.com/anarkiwi/asid-vice

# We need asid-vice for multi SID support
WORKDIR /vice/asid-vice
RUN aclocal && autoheader && autoconf && automake --force-missing --add-missing && ./autogen.sh && \
    ./configure --enable-headlessui --disable-pdf-docs --without-pulse --without-alsa --without-png --disable-dependency-tracking --disable-realdevice --disable-rs232 --disable-ipv6 --disable-native-gtk3ui --disable-sdlui --disable-sdlui2 --disable-ffmpeg
RUN make -j all && make install

COPY vsiddump.py /usr/local/bin/vsiddump.py
COPY test_vsiddump.py /usr/local/bin/test_vsiddump.py
RUN pytest /usr/local/bin/test_vsiddump.py

FROM ubuntu:latest
RUN apt-get update && apt-get install -yq libcurl4 libgomp1 zlib1g python3 python3-psutil python3-zstandard && apt -y autoremove && apt-get clean
COPY --from=builder /usr/local /usr/local
RUN /usr/local/bin/vsid --help
RUN /usr/local/bin/vsiddump.py /tmp/test.zst --help
