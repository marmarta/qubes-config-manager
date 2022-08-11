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
import pkg_resources
import subprocess
from typing import Mapping, Union, Tuple
from qubesadmin.tests import QubesTest

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk

from ..global_config.global_config import GlobalConfig
from ..global_config.policy_manager import PolicyManager

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

possible_tags = ['whonix-updatevm', 'anon-gateway']


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
            combined_properties[prop] = \
                (combined_properties[prop][0],
                 combined_properties[prop][1], str(value))
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
        ("0\x00" + "".join(f"{feature}\n" for feature, value in
                           features.items() if value is not None)).encode()
    for feature, value in features.items():
        if value is None:
            qapp.expected_calls[
                (name, "admin.vm.feature.Get", feature, None)] = \
                b'2\x00QubesFeatureNotFoundError\x00\x00' + \
                str(feature).encode() + b'\x00'
        else:
            qapp.expected_calls[
                (name, "admin.vm.feature.Get", feature, None)] = \
                b"0\x00" + str(value).encode()

    qapp.expected_calls[(name, "admin.vm.tag.List", None, None)] = \
        ("0\x00" + "".join(f"{tag}\n" for tag in tags)).encode()

    for tag in possible_tags:
        qapp.expected_calls[(name, "admin.vm.tag.Get", tag, None)] = \
            b"0\x000"

    for tag in tags:
        qapp.expected_calls[(name, "admin.vm.tag.Get", tag, None)] = \
            b"0\x001"

def add_dom0_vm_property(qapp, prop_name, prop_value):
    """Add a vm property to dom0"""
    qapp.expected_calls[('dom0', 'admin.property.Get', prop_name, None)] = \
        b'0\x00' + f'default=True type=vm {prop_value}'.encode()

def add_dom0_text_property(qapp, prop_name, prop_value):
    """Add a str property to dom0"""
    qapp.expected_calls[('dom0', 'admin.property.Get', prop_name, None)] = \
        b'0\x00' + f'default=True type=str {prop_value}'.encode()


def add_dom0_feature(qapp, feature, feature_value):
    """Add dom0 feature"""
    qapp.expected_calls[('dom0', 'admin.vm.feature.Get', feature, None)] = \
        b'0\x00' + f'{feature_value}'.encode()


@pytest.fixture
def test_qapp():
    """Test QubesApp"""
    qapp = QubesTest()
    qapp._local_name = 'dom0'  # pylint: disable=protected-access

    add_dom0_vm_property(qapp, 'clockvm', 'sys-net')
    add_dom0_vm_property(qapp, 'updatevm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_netvm', 'sys-net')
    add_dom0_vm_property(qapp, 'default_template', 'fedora-36')
    add_dom0_vm_property(qapp, 'default_dispvm', 'fedora-36')

    add_dom0_text_property(qapp, 'default_kernel', '1.1')

    add_dom0_feature(qapp, 'gui-default-allow-fullscreen', '')
    add_dom0_feature(qapp, 'gui-default-allow-utf8-titles', '')
    add_dom0_feature(qapp, 'gui-default-trayicon-mode', '')

    # setup pools:
    qapp.expected_calls[('dom0', 'admin.pool.List', None, None)] = \
        b'0\x00linux-kernel\nlvm\nfile\n'
    qapp.expected_calls[('dom0', 'admin.pool.volume.List',
                         'linux-kernel', None)] = \
        b'0\x001.1\nmisc\n4.2\n'

    add_expected_vm(qapp, 'dom0', 'AdminVM',
                    {}, {'service.qubes-update-check': 1,
                         'config.default.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'sys-net', 'AppVM',
                    {'provides_network': ('bool', False, 'True')},
                    {'service.qubes-update-check': None,
                     'service.qubes-updates-proxy': 1}, [])

    add_expected_vm(qapp, 'sys-firewall', 'AppVM',
                    {'provides_network': ('bool', False, 'True')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'fedora-36', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'fedora-35', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'default-dvm', 'DispVM',
                    {'template_for_dispvms': ('bool', False, 'True')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-vm', 'AppVM',
                    {}, {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-blue', 'AppVM',
                    {'label': ('str', False, 'blue')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'test-red', 'AppVM',
                    {'label': ('str', False, 'red')},
                    {'service.qubes-update-check': None}, [])

    add_expected_vm(qapp, 'vault', 'AppVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, [])

    return qapp

@pytest.fixture
def test_qapp_whonix(test_qapp):  # pylint: disable=redefined-outer-name
    # pylint does not understand fixtures
    """Testing qapp with qhonix vms added"""
    add_expected_vm(test_qapp, 'sys-whonix', 'AppVM',
                    {},
                    {'service.qubes-update-check': None,
                     'service.qubes-updates-proxy': 1}, ['anon-gateway'])
    add_expected_vm(test_qapp, 'anon-whonix', 'AppVM',
                    {},
                    {'service.qubes-update-check': None}, ['anon-gateway'])
    add_expected_vm(test_qapp, 'whonix-gw-15', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, ['whonix-updatevm'])
    add_expected_vm(test_qapp, 'whonix-gw-14', 'TemplateVM',
                    {"netvm": ("vm", False, '')},
                    {'service.qubes-update-check': None}, ['whonix-updatevm'])
    return test_qapp

SIGNALS_REGISTERED = False

@pytest.fixture
def test_builder():
    """Test gtk_builder with loaded test glade file and registered signals."""
    global SIGNALS_REGISTERED  # pylint:disable=global-statement
    # register all the signals various widgets might emit
    if not SIGNALS_REGISTERED:
        GlobalConfig.register_signals()
        SIGNALS_REGISTERED = True
    # test glade file contains very simple setup with correctly named widgets
    builder = Gtk.Builder()
    builder.add_from_file(pkg_resources.resource_filename(
        __name__, 'test.glade'))
    return builder

@pytest.fixture
def real_builder():
    """Gtk builder with actual config glade file registered"""
    global SIGNALS_REGISTERED  # pylint:disable=global-statement
    # register all the signals various widgets might emit
    if not SIGNALS_REGISTERED:
        GlobalConfig.register_signals()
        SIGNALS_REGISTERED = True
    # test glade file contains very simple setup with correctly named widgets
    builder = Gtk.Builder()
    builder.add_from_file(pkg_resources.resource_filename(
        __name__, '../global_config.glade'))
    return builder



class TestPolicyClient:
    """Testing policy client that does not interact with Policy API"""
    def __init__(self):
        self.file_tokens = {
            'a-test': 'a',
            'b-test': 'b'
        }
        self.files = {
            'a-test': """Test * @anyvm @anyvm deny""",
            'b-test': """Test * test-vm @anyvm allow\n
Test * test-red test-blue deny"""
        }
        self.service_to_files = {
            'Test': ['a-test', 'b-test']
        }

    def policy_get_files(self, service_name):
        """Get files connected to a given service; does not
        take into account policy_replace"""
        return self.service_to_files.get(service_name, '')

    def policy_get(self, file_name):
        """Get file contents; takes into account policy_replace."""
        if file_name in self.files:
            return self.files[file_name], self.file_tokens[file_name]
        raise subprocess.CalledProcessError(2, 'test')

    def policy_replace(self, filename, policy_text, token='any'):
        """Replace file contents with provided contents."""
        if token != 'any':
            if token != self.file_tokens.get(filename, ''):
                raise subprocess.CalledProcessError(2, 'test')
        self.files[filename] = policy_text
        self.file_tokens[filename] = str(len(policy_text))


@pytest.fixture
def test_policy_manager():
    """Policy manager with patched out object requiring actual working
    Admin API methods"""
    manager = PolicyManager()
    manager.policy_client = TestPolicyClient()
    return manager
