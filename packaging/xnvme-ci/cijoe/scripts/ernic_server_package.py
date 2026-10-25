#!/usr/bin/env python3
"""
Package the rocm-ernic server as a deb, for the hosts that serve the NIC
========================================================================

libvfio-user is built at 'xnvme_ci.libvfio_user.sha', installed beside the
server under /opt/rocm-ernic and found through the RPATH, so the package does
not depend on, or collide with, whatever libvfio-user the host has. Everything
else the server links must come from the archive, and becomes its Depends.

The deb is <version>+xnvme<n> for a release, or <version>+xnvme0~g<commit>
for a build of the branch, with 'xnvme_ci.n' as <n>.

Retargetable: true
------------------
"""
import errno
import logging as log
import shlex

PREFIX = "/opt/rocm-ernic"
VERSION = (
    "python3 -c 'import re,pathlib; t=pathlib.Path(\"CMakeLists.txt\").read_text(); "
    "print(\".\".join(re.search(rf\"set\\(ROCM_ERNIC_VERSION_{k}\\s+(\\d+)\\)\", t).group(1) "
    "for k in (\"MAJOR\",\"MINOR\",\"PATCH\")))'"
)


def deb_version(cijoe, src, n):
    """The deb version of the tree at 'src', or None"""
    err, state = cijoe.run(f"{VERSION} && git rev-parse --short HEAD", cwd=src)
    if err:
        return None, None
    base, sha = state.output().split()[-2:]
    return (f"{base}+xnvme{n}" if n else f"{base}+xnvme0~g{sha}"), sha


def main(args, cijoe):
    """Build the rocm-ernic server deb into 'xnvme_ci.out'"""

    src = cijoe.getconf("xnvme_ci.src")
    out = cijoe.getconf("xnvme_ci.out")
    n = int(cijoe.getconf("xnvme_ci.n"))
    vfu_repo = cijoe.getconf("xnvme_ci.libvfio_user.repository")
    vfu_sha = cijoe.getconf("xnvme_ci.libvfio_user.sha")

    version, sha = deb_version(cijoe, src, n)
    if not version:
        log.error(f"could not read the version of {src}")
        return errno.EINVAL
    log.info(f"packaging rocm-ernic {version}")

    # A debug build of libvfio-user adds -Werror, and its unit tests use cmocka
    # macros newer cmocka deprecates.
    err, _ = cijoe.run(
        f"work=$(mktemp -d) && echo $work > /tmp/ernic-server-work && "
        f"git clone -q {vfu_repo} $work/libvfio-user && "
        f"git -C $work/libvfio-user checkout -q {vfu_sha} && "
        f"meson setup $work/libvfio-user/build $work/libvfio-user --prefix={PREFIX} "
        "--libdir=lib --buildtype=release -Dwarning_level=0 && "
        "ninja -C $work/libvfio-user/build install && "
        f"PKG_CONFIG_PATH={PREFIX}/lib/pkgconfig cmake -S {src} -B $work/build -G Ninja "
        f"-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_PREFIX_PATH={PREFIX} "
        f"-DCMAKE_INSTALL_RPATH={PREFIX}/lib && "
        "cmake --build $work/build --target rocm-ernic"
    )
    if err:
        return err

    stage = "$work/stage"
    err, _ = cijoe.run(
        "work=$(cat /tmp/ernic-server-work) && "
        f"install -D -m 0755 $work/build/rocm-ernic {stage}{PREFIX}/bin/rocm-ernic && "
        f"mkdir -p {stage}{PREFIX}/lib {stage}/usr/bin && "
        f"cp -a {PREFIX}/lib/libvfio-user.so* {stage}{PREFIX}/lib/ && "
        f"ln -s {PREFIX}/bin/rocm-ernic {stage}/usr/bin/rocm-ernic && "
        f"install -D -m 0644 -t {stage}/usr/share/doc/rocm-ernic {src}/LICENSE.md {src}/LICENSE_GPL.md"
    )
    if err:
        return err

    # Everything but libvfio-user must come from the archive
    bins = f"{stage}{PREFIX}/bin/rocm-ernic"
    err, _ = cijoe.run(
        "work=$(cat /tmp/ernic-server-work) && "
        f"! LD_LIBRARY_PATH={stage}{PREFIX}/lib ldd {bins} | grep 'not found'"
    )
    if err:
        log.error("the server links something that is not there")
        return errno.ENOENT
    err, state = cijoe.run(
        "work=$(cat /tmp/ernic-server-work) && "
        f"ldd {bins} | awk '/=> \\// {{print $3}}' | grep -v '^{PREFIX}/' | sort -u | "
        "xargs -r realpath | xargs -r dpkg -S | cut -d: -f1 | sort -u | paste -sd, | "
        "sed 's/,/, /g'"
    )
    deps = state.output().strip().splitlines()[-1] if not err and state.output().strip() else ""
    if not deps:
        log.error("found no archive packages for the server's libraries")
        return errno.ENOENT

    err, state = cijoe.run("dpkg --print-architecture")
    arch = state.output().strip().splitlines()[-1]
    control = f"""Package: rocm-ernic
Version: {version}
Architecture: {arch}
Maintainer: Simon A. F. Lund <os@safl.dk>
Depends: {deps}
Section: misc
Priority: optional
Homepage: https://github.com/safl/rocm-ernic
Description: rocm-ernic emulated RDMA NIC, served over vfio-user
 The rocm-ernic vfio-user server from {sha}, with
 libvfio-user {vfu_sha} under {PREFIX}. The guest drives the NIC with the
 ionic-ernic drivers built from the same revision.
"""
    return cijoe.run(
        "work=$(cat /tmp/ernic-server-work) && "
        f"mkdir -p {stage}/DEBIAN {out} && "
        f"printf '%s' {shlex.quote(control)} > {stage}/DEBIAN/control && "
        f"dpkg-deb --root-owner-group -Zxz --build {stage} {out} && rm -rf $work && "
        f"ls {out}/rocm-ernic_*.deb"
    )[0]
