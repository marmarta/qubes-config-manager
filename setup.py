#!/usr/bin/env python3
''' Setup.py file '''
import setuptools.command.install

setuptools.setup(name='qubes_new_qube',
                 version='0.1',
                 author='Invisible Things Lab',
                 author_email='marmarta@invisiblethingslab.com',
                 description='Qubes Configuration Manager',
                 license='GPL2+',
                 url='https://www.qubes-os.org/',
                 packages=["qubes_new_qube"],
                 entry_points={
                     'gui_scripts': [
                         'qubes-new-qube = qubes_new_qube.new_qube_app:main',
                     ]
                 },
                 package_data={
                     'qubes_new_qube': ["new_qube.glade",
                                        "qubes-new-qube.css",
                                        "qubes-widgets-styling.css"]},
)
