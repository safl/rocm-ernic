#!/usr/bin/env python3
"""
Package the patched ionic drivers as a DKMS deb, for one kernel series
======================================================================

The ionic sources only build against a kernel of the same major.minor, so the
package for 'xnvme_ci.kernel_ref' v7.3 is ionic-ernic-7.3-dkms, and DKMS
builds it only for 7.3 kernels. It builds on install, for every installed
kernel of that series, so no reboot and no kernel of ours is needed. It also
carries the guest's rocm-ernic naming rule and loads ionic_rdma at boot,
which nothing else autoloads.

The patches are the top level of ansible/files/patches, the set the guest
images used, applied and staged by the repository's own ansible scripts.

Retargetable: true
------------------
"""
import errno
import logging as log
import shlex

from ernic_server_package import deb_version


def main(args, cijoe):
    """Build the ionic-ernic-<series>-dkms deb into 'xnvme_ci.out'"""

    src = cijoe.getconf("xnvme_ci.src")
    out = cijoe.getconf("xnvme_ci.out")
    n = int(cijoe.getconf("xnvme_ci.n"))
    kref = cijoe.getconf("xnvme_ci.kernel_ref")
    series = kref.lstrip("v")
    pkg = f"ionic-ernic-{series}-dkms"
    tree = f"/usr/src/ionic-ernic-{series}"
    scripts = f"{src}/ansible/files/scripts"

    version, sha = deb_version(cijoe, src, n)
    if not version:
        log.error(f"could not read the version of {src}")
        return errno.EINVAL
    log.info(f"packaging {pkg} {version}")

    err, _ = cijoe.run(
        f"work=$(mktemp -d) && echo $work > /tmp/ernic-dkms-work && "
        f"bash {scripts}/fetch-ionic-sources.sh --source-dir $work/ionic --kernel-ref {kref} "
        f"--patches-dir {src}/ansible/files/patches --force && "
        f"bash {scripts}/setup-ionic-dkms.sh --source-dir $work/ionic --kernel-ref {kref} "
        f"--stage-only && grep '^BUILD_EXCLUSIVE_KERNEL=' {tree}/dkms.conf"
    )
    if err:
        return err

    control = f"""Package: {pkg}
Version: {version}
Architecture: all
Maintainer: Simon A. F. Lund <os@safl.dk>
Depends: dkms
Section: kernel
Priority: optional
Homepage: https://github.com/safl/rocm-ernic
Description: ionic and ionic_rdma for rocm-ernic's emulated NIC, as DKMS, for {series} kernels
 The upstream ionic drivers at {kref} with rocm-ernic's patches from
 {sha}, built by DKMS for every installed {series} kernel,
 so they replace the in-tree drivers without a reboot. They match the
 rocm-ernic server of the same version.
"""
    conffiles = "/etc/modules-load.d/rocm-ernic.conf\n/etc/udev/rules.d/99-rocm-ernic.rules\n"
    postinst = f"""#!/bin/sh
set -e
if [ "$1" = configure ]; then
	dkms add ionic-ernic/{series} >/dev/null 2>&1 || true
	for build in /lib/modules/*/build; do
		[ -e "$build" ] || continue
		# 77 is DKMS declining a kernel outside BUILD_EXCLUSIVE_KERNEL
		dkms install ionic-ernic/{series} -k "$(basename "$(dirname "$build")")" ||
			[ $? -eq 77 ]
	done
fi
"""
    prerm = f"""#!/bin/sh
set -e
dkms remove ionic-ernic/{series} --all >/dev/null 2>&1 || true
"""
    stage = "$work/stage"
    files = {
        f"{stage}/DEBIAN/control": control,
        f"{stage}/DEBIAN/conffiles": conffiles,
        f"{stage}/DEBIAN/postinst": postinst,
        f"{stage}/DEBIAN/prerm": prerm,
        f"{stage}/etc/modules-load.d/rocm-ernic.conf": "ionic_rdma\n",
    }
    writes = " && ".join(
        f"printf '%s' {shlex.quote(body)} > {path}" for path, body in files.items()
    )
    return cijoe.run(
        "work=$(cat /tmp/ernic-dkms-work) && "
        f"mkdir -p {stage}/usr/src {stage}/etc/modules-load.d {stage}/DEBIAN {out} && "
        f"cp -a {tree} {stage}/usr/src/ && "
        f"install -D -m 0644 {src}/udev/99-rocm-ernic.rules {stage}/etc/udev/rules.d/99-rocm-ernic.rules && "
        f"install -D -m 0644 -t {stage}/usr/share/doc/{pkg} {src}/LICENSE.md {src}/LICENSE_GPL.md && "
        f"{writes} && chmod 0755 {stage}/DEBIAN/postinst {stage}/DEBIAN/prerm && "
        f"dpkg-deb --root-owner-group -Zxz --build {stage} {out} && rm -rf $work && "
        f"ls {out}/{pkg}_*.deb"
    )[0]
