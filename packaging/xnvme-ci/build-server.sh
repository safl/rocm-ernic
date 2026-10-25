#!/bin/bash
# Package the rocm-ernic server as a .deb, for the hosts that serve the NIC.
#
#   build-server.sh <output dir> <deb version>
#
# Runs as root in a container of the release the host runs. libvfio-user is
# built at the revision rocm-ernic's own CI pins, installed beside the server
# under /opt/rocm-ernic and found through the RPATH, so the package does not
# depend on, or collide with, whatever libvfio-user the host has.
#
# Copyright (c) Simon A. F. Lund <os@safl.dk>
# SPDX-License-Identifier: MIT
set -euo pipefail
out=$(realpath "$1")
version=$2
src=$(cd "$(dirname "$0")/../.." && pwd)
prefix=/opt/rocm-ernic
vfu_sha=8039244

export DEBIAN_FRONTEND=noninteractive
apt-get -qy update >/dev/null
apt-get -qy install --no-install-recommends ca-certificates git cmake meson ninja-build \
	pkg-config gcc libc6-dev libibverbs-dev librdmacm-dev libglib2.0-dev libjson-c-dev libcmocka-dev \
	file >/dev/null

work=$(mktemp -d)
git clone -q https://github.com/nutanix/libvfio-user "$work/libvfio-user"
git -C "$work/libvfio-user" checkout -q "$vfu_sha"
# A debug build adds -Werror, and its unit tests use cmocka macros newer cmocka
# deprecates.
meson setup "$work/libvfio-user/build" "$work/libvfio-user" --prefix="$prefix" \
	--libdir=lib --buildtype=release -Dwarning_level=0
ninja -C "$work/libvfio-user/build" install >/dev/null

PKG_CONFIG_PATH=$prefix/lib/pkgconfig cmake -S "$src" -B "$work/build" -G Ninja \
	-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_PREFIX_PATH="$prefix" \
	-DCMAKE_INSTALL_RPATH="$prefix/lib"
cmake --build "$work/build" --target rocm-ernic >/dev/null

stage=$work/stage
install -D -m 0755 "$work/build/rocm-ernic" "$stage$prefix/bin/rocm-ernic"
mkdir -p "$stage$prefix/lib" "$stage/usr/bin"
cp -a "$prefix"/lib/libvfio-user.so* "$stage$prefix/lib/"
ln -s "$prefix/bin/rocm-ernic" "$stage/usr/bin/rocm-ernic"
install -D -m 0644 -t "$stage/usr/share/doc/rocm-ernic" "$src/LICENSE.md" "$src/LICENSE_GPL.md"

# Everything but libvfio-user must come from the archive.
bins="$stage$prefix/bin/rocm-ernic"
if LD_LIBRARY_PATH=$stage$prefix/lib ldd $bins | grep 'not found'; then
	echo "build-server.sh: the server links something that is not there" >&2
	exit 1
fi
deps=$(ldd $bins | awk '/=> \// {print $3}' | grep -v "^$prefix/" | sort -u |
	xargs -r realpath | xargs -r dpkg -S | cut -d: -f1 | sort -u | paste -sd, |
	sed 's/,/, /g')
[ -n "$deps" ]

mkdir -p "$stage/DEBIAN"
cat >"$stage/DEBIAN/control" <<CONTROL
Package: rocm-ernic
Version: $version
Architecture: $(dpkg --print-architecture)
Maintainer: Simon A. F. Lund <os@safl.dk>
Depends: $deps
Section: misc
Priority: optional
Homepage: https://github.com/safl/rocm-ernic
Description: rocm-ernic emulated RDMA NIC, served over vfio-user
 The rocm-ernic vfio-user server from $(git -C "$src" rev-parse --short HEAD), with
 libvfio-user $vfu_sha under $prefix. The guest drives the NIC with the
 ionic-ernic drivers built from the same revision.
CONTROL
mkdir -p "$out"
dpkg-deb --root-owner-group -Zxz --build "$stage" "$out" >/dev/null
rm -rf "$work"
ls "$out"/rocm-ernic_*.deb
