/*
 * peer_mem.c - another device's memory, mapped beside the guest's
 *
 * Copyright (C) Advanced Micro Devices, Inc.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the LICENSE_GPL.md file in the top-level directory.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "parse_int.h"
#include "peer_mem.h"

#define PEER_MEM_MAX 4

struct peer_mem {
    char *path;
    size_t len;
    void *map; /* NULL until a region binds it */
    uint64_t iova;
    bool used; /* reported the first DMA it served */
};

/* Touched only from the libvfio-user thread, which is the only one that DMAs. */
static struct peer_mem peers[PEER_MEM_MAX];
static unsigned int npeers;

int ernic_peer_mem_add(const char *spec)
{
    const char *colon = strrchr(spec, ':');
    uint64_t len;
    char *path;

    if (npeers == PEER_MEM_MAX || !colon || colon == spec ||
        !ernic_parse_size(colon + 1, &len) || !len)
        return -EINVAL;
    path = strndup(spec, (size_t)(colon - spec));
    if (!path)
        return -ENOMEM;

    peers[npeers++] = (struct peer_mem){.path = path, .len = (size_t)len};
    return 0;
}

void ernic_peer_mem_bind(uint64_t iova, size_t len, const void *vaddr)
{
    if (vaddr)
        return;

    for (unsigned int i = 0; i < npeers; i++) {
        struct peer_mem *p = &peers[i];
        int fd;

        if (p->map || p->len != len)
            continue;

        /* Opened per bind: the backing file may be the peer server's memfd
         * under /proc, which only exists while that server runs. */
        fd = open(p->path, O_RDWR | O_CLOEXEC);
        if (fd < 0) {
            fprintf(stderr, "rocm-ernic: peer memory %s: %s\n", p->path,
                    strerror(errno));
            continue;
        }
        p->map = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (p->map == MAP_FAILED) {
            p->map = NULL;
            fprintf(stderr, "rocm-ernic: peer memory %s: mmap: %s\n", p->path,
                    strerror(errno));
            continue;
        }
        p->iova = iova;
        p->used = false;
        fprintf(stderr, "rocm-ernic: peer memory %s serves DMA at 0x%llx+0x%zx\n",
                p->path, (unsigned long long)iova, len);
        return;
    }
}

void ernic_peer_mem_unbind(uint64_t iova, size_t len)
{
    for (unsigned int i = 0; i < npeers; i++) {
        struct peer_mem *p = &peers[i];

        if (p->map && p->iova == iova && p->len == len) {
            munmap(p->map, p->len);
            p->map = NULL;
        }
    }
}

void *ernic_peer_mem_lookup(uint64_t gpa, size_t len)
{
    for (unsigned int i = 0; i < npeers; i++) {
        struct peer_mem *p = &peers[i];

        if (p->map && gpa >= p->iova && gpa - p->iova <= p->len &&
            len <= p->len - (gpa - p->iova)) {
            if (!p->used) {
                p->used = true;
                fprintf(stderr, "rocm-ernic: peer memory %s served DMA at 0x%llx\n",
                        p->path, (unsigned long long)gpa);
            }
            return (char *)p->map + (gpa - p->iova);
        }
    }
    return NULL;
}
