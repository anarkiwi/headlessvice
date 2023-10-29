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

WORKDIR /vice
# ENV VICEVER 3.7.1
#
# RUN apt-get update && apt-get install -yq wget && wget -q -O- https://sourceforge.net/projects/vice-emu/files/releases/vice-$VICEVER.tar.gz/download | tar zxvf -
#    apt-get install -y subversion && \
#    svn checkout --non-interactive --trust-server-cert http://svn.code.sf.net/p/vice-emu/code/tags/$VICEVER vice-emu-code

RUN apt-get update && \
    apt-get install -y git file make autoconf gcc g++ flex bison dos2unix xa65 && \
    git clone https://github.com/anarkiwi/asid-vice && \
    cd asid-vice && \
    aclocal && autoheader && autoconf && automake --force-missing --add-missing && ./autogen.sh && \
    ./configure --enable-headlessui --disable-pdf-docs --without-pulse --without-alsa --without-png --disable-dependency-tracking --disable-realdevice --disable-rs232 --disable-ipv6 --disable-native-gtk3ui --disable-sdlui --disable-sdlui2
RUN cd asid-vice && make -j all && make install

FROM ubuntu:latest

COPY --from=builder /usr/local /usr/local
COPY vsiddump.py /usr/local/bin/vsiddump.py
RUN apt-get update && apt-get install -yq libgomp1 python3 python3-pip && pip3 install psutil zstandard && apt-get purge -y python3-pip && apt -y autoremove && apt-get clean
RUN /usr/local/bin/vsid --help
RUN /usr/local/bin/vsiddump.py /tmp/test.zst --help
