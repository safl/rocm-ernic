/*
 * peer_mem.h - another device's memory, mapped beside the guest's
 *
 * Copyright (C) Advanced Micro Devices, Inc.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the LICENSE_GPL.md file in the top-level directory.
 */

#ifndef ERNIC_PEER_MEM_H
#define ERNIC_PEER_MEM_H

#include <stddef.h>
#include <stdint.h>

/*
 * QEMU announces another vfio-user device's mmap-able BAR as a DMA region
 * without a file descriptor, so libvfio-user cannot reach it and a transfer
 * into that BAR, peer-to-peer DMA, fails. When the file backing the BAR is
 * named on the command line, the first fd-less region of the same size is
 * served from a mapping of that file instead.
 */

/* Parse "<path>:<size>", the size as ernic_parse_size() takes it. The file
 * is mapped from offset 0. */
int ernic_peer_mem_add(const char *spec);

/* Called from the DMA (un)registration callbacks with every region. */
void ernic_peer_mem_bind(uint64_t iova, size_t len, const void *vaddr);
void ernic_peer_mem_unbind(uint64_t iova, size_t len);

/* Host address of [@gpa, @gpa + @len) when a bound peer covers it, or NULL. */
void *ernic_peer_mem_lookup(uint64_t gpa, size_t len);

#endif /* ERNIC_PEER_MEM_H */
