#!/usr/bin/env python3
"""
Install the rocm-ernic server deb and check what the hosts rely on
==================================================================

Installs the deb from 'xnvme_ci.out' and checks that the server finds its own
libvfio-user under /opt/rocm-ernic rather than the host's, and that it has the
'--peer-memory' option xnvme-images serves the GPU's VRAM to the NIC with.

Retargetable: true
------------------
"""
import logging as log


def main(args, cijoe):
    """Install and check the server deb"""

    out = cijoe.getconf("xnvme_ci.out")

    err, _ = cijoe.run(
        "export DEBIAN_FRONTEND=noninteractive && apt-get -qy update && "
        f"apt-get -qy install {out}/rocm-ernic_*.deb"
    )
    if err:
        return err

    err, _ = cijoe.run("ldd /opt/rocm-ernic/bin/rocm-ernic | grep /opt/rocm-ernic/lib/libvfio-user")
    if err:
        log.error("the server does not use its own libvfio-user")
        return err

    err, _ = cijoe.run("rocm-ernic --help 2>&1 | grep -- --peer-memory")
    if err:
        log.error("the server lacks --peer-memory")
    return err
