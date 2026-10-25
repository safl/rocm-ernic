# xnvme-ci packaging

Debs for xNVMe's test images, built and checked by the cijoe workflows in
`cijoe/`, which `.github/workflows/xnvme-ci.yml` runs on this fork's
`xnvme-ci/*` branches and releases on `xnvme-ci/v<version>-<n>` tags.

| Package | For | Built by |
| ------- | --- | -------- |
| `rocm-ernic` | the host: the server, with libvfio-user under `/opt/rocm-ernic` | `cijoe/workflows/server.yaml`, on the hosts' release |
| `ionic-ernic-<series>-dkms` | the guest: ionic and ionic_rdma with rocm-ernic's patches, the naming rule, ionic_rdma at boot | `cijoe/workflows/dkms.yaml`, for one kernel series |

Both come from one revision, so a server and a guest driver from the same
release always match. `dkms.yaml` checks the DKMS package against a
kernel's headers in a container; no such kernel needs to run. Either runs
outside GitHub as well, as root on that release:

    pipx install --include-deps ./packaging/xnvme-ci/cijoe
    cd packaging/xnvme-ci/cijoe
    XNVME_CI_SRC=$PWD/../../.. XNVME_CI_OUT=/tmp/debs XNVME_CI_N=0 \
      cijoe workflows/server.yaml --config configs/default.toml --monitor
