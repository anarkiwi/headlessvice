# Containerized, headless VICE, suitable for ripping SID register dumps, etc.
#
# Example usage:
#
# $ docker build -f Dockerfile . -t anarkiwi/headlessvice
# $ mkdir vice
# $ cp /somewhere/paradroid.sid ~/vice
# $ docker run --rm -v ~/vice:/vice -ti anarkiwi/headlessvice vsid -verbose -sounddev dump -soundarg /vice/paradroid.dump -warp -limit 10000000 /vice/paradroid.sid
#
# $ SIDS=/sids ; cd $SIDS && find . -type f -name \*sid|parallel docker run --rm -v $SIDS:/vice -i anarkiwi/headlessvice vsid -sounddev dump -soundarg /vice/`basename {}`.dump -warp -limit 300000000 /vice/{}

FROM ubuntu:latest AS builder

WORKDIR /vice

RUN apt-get update && apt-get install -y subversion && \
    svn checkout --non-interactive --trust-server-cert http://svn.code.sf.net/p/vice-emu/code/tags/v3.5 vice-emu-code

RUN apt-get update && \
    apt-get install -y libx11-dev file make autoconf gcc g++ flex bison dos2unix xa65 && \
    cd vice-emu-code/vice && \
    aclocal && autoheader && autoconf && automake --force-missing --add-missing && ./autogen.sh && \
    ./configure --enable-headlessui --disable-pdf-docs --without-pulse --without-alsa --without-png --disable-dependency-tracking --disable-realdevice --disable-rs232 --disable-ipv6 --disable-native-gtk3ui --disable-sdlui --disable-sdlui2 && \
    make -j4 && \
    make install

FROM ubuntu:latest

COPY --from=builder /usr/local /usr/local
