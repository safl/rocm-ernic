#!/bin/bash
# Install an ionic-ernic DKMS package against a kernel's headers and check that
# DKMS built both drivers for it, and that a kernel of another series is
# skipped rather than failing the install. Needs no such kernel running.
#
#   test-dkms.sh <deb> <kernel release>, e.g. 7.3.0-9-generic
#
# Copyright (c) Simon A. F. Lund <os@safl.dk>
# SPDX-License-Identifier: MIT
set -euo pipefail
deb=$(realpath "$1")
kver=$2

export DEBIAN_FRONTEND=noninteractive
apt-get -qy update >/dev/null
apt-get -qy install --no-install-recommends dkms kmod "linux-headers-$kver" >/dev/null
# A kernel outside the series, by its headers only: DKMS must decline it.
other=6.6.0-1-other
mkdir -p "/lib/modules/$other"
ln -s "/usr/src/linux-headers-$kver" "/lib/modules/$other/build"

apt-get -qy install --no-install-recommends "$deb" >/dev/null
dkms status
# Only the headers are installed, so there is no modules.dep for modinfo to
# search; the files DKMS installed are the evidence.
for mod in ionic ionic_rdma; do
	if ! compgen -G "/lib/modules/$kver/updates/dkms/$mod.ko*" >/dev/null; then
		echo "test-dkms.sh: no DKMS $mod for $kver" >&2
		exit 1
	fi
	echo "$mod: $(ls /lib/modules/"$kver"/updates/dkms/"$mod".ko*)"
done
if compgen -G "/lib/modules/$other/updates/dkms/ionic*" >/dev/null; then
	echo "test-dkms.sh: built for $other, outside the series" >&2
	exit 1
fi
test -s /etc/udev/rules.d/99-rocm-ernic.rules
grep -qx ionic_rdma /etc/modules-load.d/rocm-ernic.conf

apt-get -qy purge "$(dpkg-deb -f "$deb" Package)" >/dev/null
# Captured first: under pipefail, grep -q stopping early could let a match
# read as no match.
if grep -q ionic-ernic <<<"$(dkms status)"; then
	echo "test-dkms.sh: purge left the DKMS module registered" >&2
	exit 1
fi
echo "test-dkms.sh: ok"
