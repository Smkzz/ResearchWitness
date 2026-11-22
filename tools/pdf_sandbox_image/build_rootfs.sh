#!/bin/sh
set -eu
export LC_ALL=C
umask 022
printf '%s\n' 'Acquire::http::Proxy "http://127.0.0.1:9";' 'Acquire::http::Proxy::snapshot.debian.org "DIRECT";' 'Acquire::https::Proxy "http://127.0.0.1:9";' > /etc/apt/apt.conf.d/99-source-boundary
rm -f /etc/apt/sources.list.d/*
printf '%s\n' 'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://snapshot.debian.org/archive/debian/20261120T000000Z/ trixie main' > /etc/apt/sources.list
apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=30 -o Debug::Acquire::http=true -o APT::Update::Error-Mode=any update
cp /var/lib/apt/lists/*_InRelease /work/InRelease
cd /work
sha256sum -c inrelease.sha256
mkdir -p /tmp/pdf-build/debs /tmp/pdf-build/stage /tmp/pdf-build/rootfs
chmod 755 /tmp/pdf-build
chown _apt /tmp/pdf-build/debs
cd /tmp/pdf-build/debs
while read -r name version arch filename hash; do
    apt-get -o Debug::Acquire::http=true download "$name:$arch=$version"
    file=$(find . -maxdepth 1 -name "${name}_*.deb" -type f)
    test -f "$file"
    printf '%s  %s\n' "$hash" "$file" | sha256sum -c -
    dpkg-deb -x "$file" /tmp/pdf-build/stage
done < /work/lock.tsv
cd /tmp/pdf-build/stage
mkdir -p /tmp/pdf-build/rootfs/usr/bin /tmp/pdf-build/rootfs/usr/lib/x86_64-linux-gnu /tmp/pdf-build/rootfs/lib64
cp -p usr/bin/pdftotext /tmp/pdf-build/rootfs/usr/bin/
loader=usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
"/tmp/pdf-build/stage/$loader" --list --library-path /tmp/pdf-build/stage/usr/lib/x86_64-linux-gnu /tmp/pdf-build/stage/usr/bin/pdftotext > /work/libraries.txt
awk '/=> \/tmp\/pdf-build\/stage\// {print $3}' /work/libraries.txt > /work/library-paths.txt
printf '/tmp/pdf-build/stage/%s\n' "$loader" >> /work/library-paths.txt
while IFS= read -r lib; do
    cp -pL "$lib" /tmp/pdf-build/rootfs/usr/lib/x86_64-linux-gnu/
done < /work/library-paths.txt
ln -s /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 /tmp/pdf-build/rootfs/lib64/ld-linux-x86-64.so.2
for data in usr/share/poppler usr/share/fonts etc/fonts usr/share/fontconfig; do
    if test -d "$data"; then
        mkdir -p "/tmp/pdf-build/rootfs/$(dirname "$data")"
        cp -a "$data" "/tmp/pdf-build/rootfs/$data"
    fi
done
find usr/share/doc -name copyright -type f | sort | while IFS= read -r license; do
    mkdir -p "/tmp/pdf-build/rootfs/$(dirname "$license")"
    cp -p "$license" "/tmp/pdf-build/rootfs/$license"
done
cd /tmp/pdf-build/rootfs
find . -type d -exec chmod 755 {} +
find . -exec touch -h -d '2026-11-20 00:00:00 UTC' {} +
find . -printf '%P\t%m\t%s\t%l\n' | sort > /work/stat-inventory.tsv
find . -type f -print0 | sort -z | xargs -0 sha256sum > /work/file-hashes.txt
tar --sort=name --mtime='2026-11-20 00:00:00 UTC' --owner=0 --group=0 --numeric-owner -cf /work/rootfs.tar .
sha256sum /work/rootfs.tar
