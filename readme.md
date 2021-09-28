## Configuration Manager for Qubes OS

This is a preliminary draft of a configuration manager tool for Qubes OS.
Intented to make system settings usable for non-power users. 

## Planned steps

Formalized design, user research.

## Initial ideas for configuration

File format for configuration:
- yaml

with a list named 'preconfigured'. Each position of the list must contain the
following mappings:
- name
- subtitle
- salt

and may contain any optional mappings. Currently supported:
- icon (must refer to a png icon file of size of at least 32x32 px)

Also the file may contain the following mappings:
network_settings:
that maps to a list of mappings  of options. Currently supported:
- enable_wifi: True
- enable_wired: True

vpn_settings:
  enable_vpn: True


