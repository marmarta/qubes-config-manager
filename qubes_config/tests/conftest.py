# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2022 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
"""Conftest helper pytest file: fixtures container here are
 reachable by all tests"""
import pytest
from typing import Mapping, Union, Tuple
from qubesadmin.tests import QubesTest

default_vm_properties = {
    "autostart": ("bool", True, "False"),
    "backup_timestamp": ("int", True, ""),
    "debug": ("bool", True, "False"),
    "default_user": ("str", True, "user"),
    "dns": ("str", True, "10.139.1.1 10.139.1.2"),
    "gateway": ("str", True, ""),
    "gateway6": ("str", True, ""),
    "icon": ("str", True, "appvm-green"),
    "include_in_backups": ("bool", True, "True"),
    "installed_by_rpm": ("bool", True, "False"),
    "ip": ("str", True, "10.137.0.2"),
    "ip6": ("str", True, ""),
    "kernel": ("str", True, "5.15.52-1.fc32"),
    "keyboard_layout": ("str", True, "us++"),
    "klass": ("str", True, "AppVM"),
    "label": ("label", False, "green"),
    "mac": ("str", True, "00:16:3e:5e:6c:00"),
    "maxmem": ("int", True, "4000"),
    "memory": ("int", True, "400"),
    "name": ("str", False, "testvm"),
    "provides_network": ("bool", True, "False"),
    "qid": ("int", False, "2"),
    "qrexec_timeout": ("int", True, "60"),
    "shutdown_timeout": ("int", True, "60"),
    "start_time": ("str", True, ""),
    "stubdom_mem": ("int", True, ""),
    "stubdom_xid": ("str", True, "-1"),
    "template_for_dispvms": ("bool", True, "False"),
    "updateable": ("bool", True, "False"),
    "uuid": ("str", False, "8fd73e95-a74b-4bf0-a87d-9978dbd1d8a4"),
    "vcpus": ("int", True, "2"),
    "virt_mode": ("str", True, "pvh"),
    "visible_gateway": ("str", True, "10.137.0.1"),
    "visible_gateway6": ("str", True, ""),
    "visible_ip": ("str", True, "10.137.0.2"),
    "visible_ip6": ("str", True, ""),
    "visible_netmask": ("str", True, "255.255.255.255"),
    "xid": ("str", True, "2"),
    "audiovm": ("vm", True, "dom0"),
    "default_dispvm": ("vm", False, "default-dvm"),
    "guivm": ("vm", True, "dom0"),
    "kernelopts": ("str", True, ""),
    "management_dispvm": ("vm", True, "default-mgmt-dvm"),
    "netvm": ("vm", False, "sys-firewall"),
    "template": ("vm", False, "fedora-36"),
}


def add_expected_vm(qapp,
                    name: str,
                    klass: str,
                    properties: Mapping[str,
                                        Union[bool, str, int,
                                              Tuple[str, bool, str]]],
                    features,
                    tags):
    """Generate expected_calls entries to get info about a VM
    :param qapp: QubesTest object
    :param name: name of the VM
    :param klass: class of the VM (AppVM, TemplateVM etc)
    :param properties: dict of properties; values can be either a value
        directly, or tuple of (type, is_default, value)
    :param features: dict of expected features - use 'None' as value for
        feature that will be checked but is not present
    :param tags: list of tags
    :return:
    """
    vm_list_call = ('dom0', 'admin.vm.List', None, None)
    vm_list = b'0\x00'
    if vm_list_call in qapp.expected_calls:
        vm_list = qapp.expected_calls[vm_list_call]
    vm_list += f'{name} class={klass} state=Halted\n'.encode()
    qapp.expected_calls[vm_list_call] = vm_list
    properties_getall = b"0\x00"
    combined_properties = default_vm_properties.copy()
    for prop, value in properties.items():
        if isinstance(value, tuple):
            combined_properties[prop] = value
        elif value is None:
            try:
                del combined_properties[prop]
            except KeyError:
                pass
        elif prop in combined_properties:
            combined_properties[prop][2] = str(value)
        else:
            raise KeyError(f"Unknown property '{prop}'")

    if klass in ("TemplateVM", "StandaloneVM"):
        del combined_properties["template"]

    for prop, value in combined_properties.items():
        prop_line = f"default={value[1]} type={value[0]} {value[2]}"
        properties_getall += (f"{prop} " + prop_line + "\n").encode()
        qapp.expected_calls[(name, "admin.vm.property.Get", prop, None)] = \
            b"0\x00" + prop_line.encode()

    qapp.expected_calls[(name, "admin.vm.feature.List", None, None)] = \
        ("0\x00" + "".join(f"{feature}\n" for feature in features)).encode()
    for feature, value in features:
        qapp.expected_calls[(name, "admin.vm.feature.Get", feature, None)] = \
            b"0\x00" + value.encode()

    qapp.expected_calls[(name, "admin.vm.tag.List", None, None)] = \
        ("0\x00" + "".join(f"{tag}\n" for tag in tags)).encode()
    for tag in tags:
        qapp.expected_calls[(name, "admin.vm.tag.Get", tag, None)] = \
            b"0\x001"
@pytest.fixture
def test_qapp():
    """Test QubesApp"""
    qapp = QubesTest()

    add_expected_vm(qapp, 'test-vm', 'AppVM',
                    {}, {}, [])
    add_expected_vm(qapp, 'test-blue', 'AppVM',
                    {'label': ('str', False, 'blue')}, {}, [])
    add_expected_vm(qapp, 'test-red', 'AppVM',
                    {'label': ('str', False, 'red')}, {}, [])
    add_expected_vm(qapp, 'vault', 'AppVM',
                    {"netvm": ("vm", False, "None")}, {}, [])

    return qapp
