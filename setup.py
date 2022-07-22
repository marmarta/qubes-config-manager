#!/usr/bin/env python3
''' Setup.py file '''
import setuptools.command.install

setuptools.setup(name='qubes_config',
                 version='0.1',
                 author='Invisible Things Lab',
                 author_email='marmarta@invisiblethingslab.com',
                 description='Qubes Configuration Manager',
                 license='GPL2+',
                 url='https://www.qubes-os.org/',
                 packages=["qubes_config", "qubes_config.global_config", "qubes_config.widgets", "qubes_config.new_qube"],
                 entry_points={
                     'gui_scripts': [
                         'qubes-new-qube = qubes_config.new_qube.new_qube_app:main',
                         'qubes-global-config = qubes_config.global_config.global_config:main'
                     ]
                 },
                 package_data={
                     'qubes_config': ["new_qube.glade",
                                      "qubes-new-qube.css",
                                      "global_config.glade",
                                      "qubes-global-config.css",
                                      "qubes-widgets-styling.css"]},
)
