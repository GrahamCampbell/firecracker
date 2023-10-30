# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the net device."""

import re
import time

import pytest

from framework import utils

# The iperf version to run this tests with
IPERF_BINARY = "iperf3"


def test_high_ingress_traffic(uvm_plain_any):
    """
    Run iperf rx with high UDP traffic.
    """
    test_microvm = uvm_plain_any
    test_microvm.spawn()
    test_microvm.basic_config()

    # Create tap before configuring interface.
    test_microvm.add_net_iface()
    tap = test_microvm.iface["eth0"]["tap"]
    guest_ip = test_microvm.iface["eth0"]["iface"].guest_ip
    # Set the tap's tx queue len to 5. This increases the probability
    # of filling the tap under high ingress traffic.
    tap.set_tx_queue_len(5)

    # Start the microvm.
    test_microvm.start()

    # Start iperf3 server on the guest.
    test_microvm.ssh.run("{} -sD\n".format(IPERF_BINARY))
    time.sleep(1)

    # Start iperf3 client on the host. Send 1Gbps UDP traffic.
    # If the net device breaks, iperf will freeze. We have to use a timeout.
    utils.run_cmd(
        "timeout 30 {} {} -c {} -u -V -b 1000000000 -t 30".format(
            test_microvm.netns.cmd_prefix(),
            IPERF_BINARY,
            guest_ip,
        ),
    )

    # Check if the high ingress traffic broke the net interface.
    # If the net interface still works we should be able to execute
    # ssh commands.
    test_microvm.ssh.check_output("echo success\n")


def test_multi_queue_unsupported(uvm_plain):
    """
    Creates multi-queue tap device and tries to add it to firecracker.
    """
    microvm = uvm_plain
    microvm.spawn()
    microvm.basic_config()

    tapname = microvm.id[:8] + "tap1"

    utils.check_output(f"ip tuntap add name {tapname} mode tap multi_queue")
    utils.check_output(f"ip link set {tapname} netns {microvm.netns.id}")

    expected_msg = re.escape(
        "Could not create the network device: Open tap device failed:"
        " Error while creating ifreq structure: Invalid argument (os error 22)."
        f" Invalid TUN/TAP Backend provided by {tapname}. Check our documentation on setting"
        " up the network devices."
    )

    with pytest.raises(RuntimeError, match=expected_msg):
        microvm.api.network.put(
            iface_id="eth0",
            host_dev_name=tapname,
            guest_mac="AA:FC:00:00:00:01",
        )

    # clean TAP device
    utils.run_cmd(f"{microvm.netns.cmd_prefix()} ip link del name {tapname}")


@pytest.fixture
def uvm_any(microvm_factory, uvm_fun, guest_kernel, rootfs_ubuntu_22):
    """Return uvm"""
    return uvm_fun(microvm_factory, guest_kernel, rootfs_ubuntu_22, None)


def test_tap_offload(uvm_any):
    """
    Verify that tap offload features are configured for a booted/restored VM.

    - Start a socat UDP server in the guest.
    - Try to send a UDP message with UDP offload enabled.

    If tap offload features are not configured, an attempt to send a message will fail with EIO "Input/output error".
    More info (search for "TUN_F_CSUM is a must"): https://blog.cloudflare.com/fr-fr/virtual-networking-101-understanding-tap/
    """
    vm = uvm_any
    port = "81"
    out_filename = "/tmp/out.txt"
    message = "x"

    # Start a UDP server in the guest
    # vm.ssh.check_output(f"nohup socat UDP-LISTEN:{port} - > {out_filename} &")
    vm.ssh.check_output(
        f"nohup socat UDP-LISTEN:{port} OPEN:{out_filename},creat > /dev/null 2>&1 &"
    )

    # Try to send a UDP message from host with UDP offload enabled
    cmd = f"ip netns exec {vm.ssh_iface().netns} python3 ./host_tools/udp_offload.py {vm.ssh_iface().host} {port}"
    ret = utils.run_cmd(cmd)

    # Check that the transmission was successful
    assert ret.returncode == 0, f"{ret.stdout=} {ret.stderr=}"

    # Check that the server received the message
    ret = vm.ssh.run(f"cat {out_filename}")
    assert ret.stdout == message, f"{ret.stdout=} {ret.stderr=}"
