#!/bin/bash
# Package the patched ionic drivers as a DKMS .deb, one per kernel series, for
# the guests that drive the NIC.
#
#   build-dkms.sh <output dir> <deb version> <kernel ref>, e.g. v7.3
#
# The ionic sources only build against a kernel of the same major.minor, so
# the package for v7.3 is ionic-ernic-7.3-dkms, and DKMS builds it only for
# 7.3 kernels. It builds on install, for every installed kernel of that
# series, so no reboot and no kernel of ours is needed. It also carries the
# guest's rocm-ernic naming rule and loads ionic_rdma at boot, which nothing
# else autoloads.
#
# Copyright (c) Simon A. F. Lund <os@safl.dk>
# SPDX-License-Identifier: MIT
set -euo pipefail
out=$(realpath "$1")
version=$2
kref=$3
src=$(cd "$(dirname "$0")/../.." && pwd)
scripts=$src/ansible/files/scripts

export DEBIAN_FRONTEND=noninteractive
apt-get -qy update >/dev/null
apt-get -qy install --no-install-recommends ca-certificates git sudo >/dev/null

work=$(mktemp -d)
# The same patch set the guest images used: the top level of patches/.
bash "$scripts/fetch-ionic-sources.sh" --source-dir "$work/ionic" --kernel-ref "$kref" \
	--patches-dir "$src/ansible/files/patches" --force >/dev/null
bash "$scripts/setup-ionic-dkms.sh" --source-dir "$work/ionic" --kernel-ref "$kref" \
	--stage-only >/dev/null

series=${kref#v}
pkg=ionic-ernic-$series-dkms
tree=/usr/src/ionic-ernic-$series
grep -q '^BUILD_EXCLUSIVE_KERNEL=' "$tree/dkms.conf"
stage=$work/stage
mkdir -p "$stage/usr/src"
cp -a "$tree" "$stage/usr/src/"
install -D -m 0644 "$src/udev/99-rocm-ernic.rules" "$stage/etc/udev/rules.d/99-rocm-ernic.rules"
mkdir -p "$stage/etc/modules-load.d"
echo ionic_rdma >"$stage/etc/modules-load.d/rocm-ernic.conf"
install -D -m 0644 -t "$stage/usr/share/doc/$pkg" "$src/LICENSE.md" "$src/LICENSE_GPL.md"

mkdir -p "$stage/DEBIAN"
cat >"$stage/DEBIAN/control" <<CONTROL
Package: $pkg
Version: $version
Architecture: all
Maintainer: Simon A. F. Lund <os@safl.dk>
Depends: dkms
Section: kernel
Priority: optional
Homepage: https://github.com/safl/rocm-ernic
Description: ionic and ionic_rdma for rocm-ernic's emulated NIC, as DKMS, for $series kernels
 The upstream ionic drivers at $kref with rocm-ernic's patches from
 $(git -C "$src" rev-parse --short HEAD), built by DKMS for every installed $series kernel,
 so they replace the in-tree drivers without a reboot. They match the
 rocm-ernic server of the same version.
CONTROL
echo "/etc/modules-load.d/rocm-ernic.conf" >"$stage/DEBIAN/conffiles"
echo "/etc/udev/rules.d/99-rocm-ernic.rules" >>"$stage/DEBIAN/conffiles"
cat >"$stage/DEBIAN/postinst" <<POSTINST
#!/bin/sh
set -e
if [ "\$1" = configure ]; then
	dkms add ionic-ernic/$series >/dev/null 2>&1 || true
	for build in /lib/modules/*/build; do
		[ -e "\$build" ] || continue
		# 77 is DKMS declining a kernel outside BUILD_EXCLUSIVE_KERNEL
		dkms install ionic-ernic/$series -k "\$(basename "\$(dirname "\$build")")" ||
			[ \$? -eq 77 ]
	done
fi
POSTINST
cat >"$stage/DEBIAN/prerm" <<PRERM
#!/bin/sh
set -e
dkms remove ionic-ernic/$series --all >/dev/null 2>&1 || true
PRERM
chmod 0755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"
mkdir -p "$out"
dpkg-deb --root-owner-group -Zxz --build "$stage" "$out" >/dev/null
rm -rf "$work"
ls "$out/${pkg}_"*.deb
