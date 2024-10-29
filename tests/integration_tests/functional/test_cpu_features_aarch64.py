# Copyright 2023 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the CPU features for aarch64."""

import pytest

from framework import utils
from framework.properties import global_props
from framework.utils_cpuid import CpuModel

pytestmark = pytest.mark.skipif(
    global_props.cpu_architecture != "aarch64", reason="Only run in aarch64"
)

G2_FEATS = set(
    (
        "fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp "
        "asimdhp cpuid asimdrdm lrcpc dcpop asimddp ssbs"
    ).split(" ")
)

G3_FEATS = G2_FEATS | set(
    "sha512 asimdfhm dit uscat ilrcpc flagm jscvt fcma sha3 sm3 sm4 rng dcpodp i8mm bf16 dgh".split(
        " "
    )
)

G3_SVE_AND_PAC = set("paca pacg sve svebf16 svei8mm".split(" "))

GET_CPU_FLAGS_CMD = r"lscpu |grep -oP '^Flags:\s+\K.+'"


def parse_cpu_flags(stdout):
    """Parse CPU flags from `lscpu`"""
    return set(stdout.strip().split(" "))


def test_guest_cpu_features(uvm_any):
    """Check the CPU features for a microvm with different CPU templates"""

    vm = uvm_any
    expected_cpu_features = set()
    match global_props.cpu_model, vm.cpu_template_name:
        case CpuModel.ARM_NEOVERSE_N1, "v1n1":
            expected_cpu_features = G2_FEATS
        case CpuModel.ARM_NEOVERSE_N1, None:
            expected_cpu_features = G2_FEATS

        # [cm]7g with guest kernel 5.10 and later
        case CpuModel.ARM_NEOVERSE_V1, "v1n1":
            expected_cpu_features = G2_FEATS
        case CpuModel.ARM_NEOVERSE_V1, "aarch64_with_sve_and_pac":
            expected_cpu_features = G3_FEATS | G3_SVE_AND_PAC
        case CpuModel.ARM_NEOVERSE_V1, None:
            expected_cpu_features = G3_FEATS

    guest_feats = parse_cpu_flags(vm.ssh.check_output(GET_CPU_FLAGS_CMD).stdout)
    assert guest_feats == expected_cpu_features


def test_host_vs_guest_cpu_features(uvm_nano):
    """Check CPU features host vs guest"""

    vm = uvm_nano
    vm.add_net_iface()
    vm.start()
    host_feats = parse_cpu_flags(utils.check_output(GET_CPU_FLAGS_CMD).stdout)
    guest_feats = parse_cpu_flags(vm.ssh.check_output(GET_CPU_FLAGS_CMD).stdout)

    if global_props.cpu_model == CpuModel.ARM_NEOVERSE_N1:
        assert host_feats - guest_feats == set()
        assert guest_feats - host_feats == {"ssbs"}
    elif global_props.cpu_model == CpuModel.ARM_NEOVERSE_V1:
        assert host_feats - guest_feats == G3_SVE_AND_PAC
        assert guest_feats - host_feats == {"ssbs"}
    else:
        # Fail the test. Pytest should print the local variables, from where we
        # can copy the CPU features
        assert False, f"Please onboard new CpuModel {global_props.cpu_model}"
