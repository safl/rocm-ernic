#!/usr/bin/env python3
"""
Install the ionic-ernic DKMS deb against a kernel's headers and check the build
===============================================================================

Installs the deb from 'xnvme_ci.out' with the headers of
'xnvme_ci.test_kernel' and checks that DKMS built both drivers for it, that a
kernel of another series is skipped rather than failing the install, and that
the naming rule and the ionic_rdma autoload are in place. Then purges it and
checks DKMS forgot it. Needs no such kernel running: only the headers are
installed, so the files DKMS installed are the evidence, not modinfo.

Retargetable: true
------------------
"""
import errno
import logging as log

OTHER = "6.6.0-1-other"


def main(args, cijoe):
    """Check the ionic-ernic DKMS build for 'xnvme_ci.test_kernel'"""

    out = cijoe.getconf("xnvme_ci.out")
    kver = cijoe.getconf("xnvme_ci.test_kernel")

    err, _ = cijoe.run(
        "export DEBIAN_FRONTEND=noninteractive && apt-get -qy update && "
        f"apt-get -qy install --no-install-recommends dkms kmod linux-headers-{kver} && "
        f"mkdir -p /lib/modules/{OTHER} && "
        f"ln -sfn /usr/src/linux-headers-{kver} /lib/modules/{OTHER}/build && "
        f"apt-get -qy install --no-install-recommends {out}/ionic-ernic-*-dkms_*.deb && dkms status"
    )
    if err:
        log.error(f"the DKMS package did not install against {kver}")
        return err

    for mod in ["ionic", "ionic_rdma"]:
        err, _ = cijoe.run(f"ls /lib/modules/{kver}/updates/dkms/{mod}.ko*")
        if err:
            log.error(f"no DKMS {mod} for {kver}")
            return err

    err, _ = cijoe.run(f"ls /lib/modules/{OTHER}/updates/dkms/ionic*")
    if not err:
        log.error(f"DKMS built ionic for {OTHER}, outside the series")
        return errno.EINVAL

    err, _ = cijoe.run(
        "test -s /etc/udev/rules.d/99-rocm-ernic.rules && "
        "grep -x ionic_rdma /etc/modules-load.d/rocm-ernic.conf"
    )
    if err:
        log.error("the naming rule or the ionic_rdma autoload is missing")
        return err

    err, _ = cijoe.run(
        f"apt-get -qy purge $(dpkg-deb -f $(ls {out}/ionic-ernic-*-dkms_*.deb) Package) && "
        "! dkms status | grep ionic-ernic"
    )
    if err:
        log.error("the purge left the DKMS module registered")
    return err
