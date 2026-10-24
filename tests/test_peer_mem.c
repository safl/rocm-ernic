/*
 * Unit tests for peer_mem.c, the mapping that serves DMA into another
 * device's BAR.
 *
 * The peer is a memfd reached through /proc/self/fd, as a real peer server's
 * memfd is reached through /proc/<pid>/fd. The checks cover which regions
 * bind, that a binding reaches the file's own bytes, and the bounds of a
 * lookup, which takes guest-controlled addresses and lengths.
 *
 * Copyright (C) Advanced Micro Devices, Inc.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the LICENSE_GPL.md file in the top-level directory.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "peer_mem.h"

#define PEER_LEN 0x10000
#define IOVA 0xe0000000000ULL

static int failures;

static void expect(bool ok, const char *what)
{
    if (ok)
        return;
    printf("  FAIL: %s\n", what);
    failures++;
}

int main(void)
{
    char path[64], spec[96];
    int fd = memfd_create("test-peer", 0);

    printf("peer memory unit tests\n");
    if (fd < 0 || ftruncate(fd, PEER_LEN) != 0) {
        perror("memfd");
        return 1;
    }
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);

    static const char *const bad[] = {
        "no-size", ":64K", "/x:", "/x:0", "/x:12Q", "/x:64KK",
        "/x:99999999999999999G",
    };
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        if (ernic_peer_mem_add(bad[i]) == 0) {
            printf("  FAIL: accepted '%s'\n", bad[i]);
            failures++;
        }
    }

    snprintf(spec, sizeof(spec), "%s:64K", path);
    expect(ernic_peer_mem_add(spec) == 0, "a valid spec must be accepted");

    /* Only an fd-less region of exactly the peer's size binds. */
    ernic_peer_mem_bind(IOVA, PEER_LEN, (void *)0x1000);
    expect(!ernic_peer_mem_lookup(IOVA, 1), "a region with a mapping must not bind");
    ernic_peer_mem_bind(IOVA, PEER_LEN * 2, NULL);
    expect(!ernic_peer_mem_lookup(IOVA, 1), "a region of another size must not bind");
    ernic_peer_mem_bind(IOVA, PEER_LEN, NULL);

    uint8_t *base = ernic_peer_mem_lookup(IOVA, PEER_LEN);
    expect(base != NULL, "the whole bound region must resolve");
    if (base) {
        uint8_t got = 0;

        base[0x1234] = 0xa5;
        expect(pread(fd, &got, 1, 0x1234) == 1 && got == 0xa5,
               "a write through the binding must reach the file");
    }

    expect(ernic_peer_mem_lookup(IOVA + PEER_LEN - 1, 1) == base + PEER_LEN - 1,
           "the last byte must resolve");
    expect(!ernic_peer_mem_lookup(IOVA + PEER_LEN - 1, 2), "one byte past the end must not resolve");
    expect(!ernic_peer_mem_lookup(IOVA - 1, 1), "one byte below the start must not resolve");
    expect(!ernic_peer_mem_lookup(IOVA + 1, SIZE_MAX),
           "a length that wraps the end must not resolve");
    expect(!ernic_peer_mem_lookup(UINT64_MAX, 1), "the top of the address space must not resolve");

    /* Unbinding forgets the region; the next fd-less region takes its place. */
    ernic_peer_mem_unbind(IOVA, PEER_LEN);
    expect(!ernic_peer_mem_lookup(IOVA, 1), "an unbound region must not resolve");
    ernic_peer_mem_bind(IOVA * 2, PEER_LEN, NULL);
    expect(ernic_peer_mem_lookup(IOVA * 2 + 0x1234, 1) != NULL,
           "a rebind at another address must resolve");
    base = ernic_peer_mem_lookup(IOVA * 2, 1);
    expect(base && base[0x1234] == 0xa5, "a rebind must map the same file");

    if (failures) {
        printf("FAILED: %d check(s)\n", failures);
        return 1;
    }
    printf("PASSED\n");
    return 0;
}
