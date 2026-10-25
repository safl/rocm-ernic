# xnvme-ci packaging

Debs for xNVMe's test images, built by `.github/workflows/xnvme-ci.yml` on
this fork's `xnvme-ci/*` branches and released on `xnvme-ci/v<version>-<n>`
tags.

| Package | For | Built by |
| ------- | --- | -------- |
| `rocm-ernic` | the host: the server, with libvfio-user under `/opt/rocm-ernic` | `build-server.sh`, in the host's release |
| `ionic-ernic-<series>-dkms` | the guest: ionic and ionic_rdma with rocm-ernic's patches, the naming rule, ionic_rdma at boot | `build-dkms.sh`, for one kernel series |

Both come from one revision, so a server and a guest driver from the same
release always match. `test-dkms.sh` builds the DKMS package against a
kernel's headers in a container; no such kernel needs to run.
