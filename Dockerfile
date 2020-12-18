# Containerized, headless VICE, suitable for ripping SID register dumps, etc.
#
# Example usage:
#
# $ docker build -f Dockerfile . -t anarkiwi/headlessvice
# $ mkdir vice
# $ cp /somewhere/paradroid.sid ~/vice
# $ docker run -v ~/vice:/vice -ti anarkiwi/headlessvice vsid -verbose -sounddev dump -soundarg /vice/paradroid.dump -warp -limit 10000000 /vice/paradroid.sid
# $ ls -l ~/vice

FROM ubuntu:latest AS builder

WORKDIR /vice

RUN apt-get update && \
    apt-get install -y libx11-dev file make autoconf gcc g++ flex bison dos2unix xa65 subversion && \
    svn checkout --non-interactive --trust-server-cert https://svn.code.sf.net/p/vice-emu/code/trunk vice-emu-code && \
    cd vice-emu-code/vice && \
    aclocal && autoheader && autoconf && automake --force-missing --add-missing && ./autogen.sh && \
    ./configure --enable-headlessui --disable-pdf-docs --without-pulse --without-alsa --without-png --disable-dependency-tracking --disable-realdevice --disable-rs232 --disable-ipv6 --disable-native-gtk3ui --disable-sdlui --disable-sdlui2 && \
    make && \
    make install

FROM ubuntu:latest

COPY --from=builder /usr/local /usr/local
