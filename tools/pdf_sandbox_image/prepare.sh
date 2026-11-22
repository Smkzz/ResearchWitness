#!/bin/sh
set -eu
export LC_ALL=C
printf '%s\n' 'Acquire::http::Proxy "http://127.0.0.1:9";' 'Acquire::http::Proxy::snapshot.debian.org "DIRECT";' 'Acquire::https::Proxy "http://127.0.0.1:9";' > /etc/apt/apt.conf.d/99-source-boundary
rm -f /etc/apt/sources.list.d/*
printf '%s\n' 'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://snapshot.debian.org/archive/debian/20261120T000000Z/ trixie main' > /etc/apt/sources.list
apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=30 -o Debug::Acquire::http=true -o Debug::Acquire::sqv=true -o Debug::pkgAcquire::Auth=true -o APT::Update::Error-Mode=any update
cp /var/lib/apt/lists/*_InRelease /work/InRelease
sha256sum /work/InRelease
apt-get -s -o Dir::State::status=/dev/null --no-install-recommends install poppler-utils > /work/resolution.txt
awk '/^Inst / {print $2 "=" substr($3,2)}' /work/resolution.txt > /work/versions.txt
mkdir /work/metadata
while IFS= read -r spec; do
    apt-cache show "$spec" > "/work/metadata/${spec%%=*}.txt"
done < /work/versions.txt
