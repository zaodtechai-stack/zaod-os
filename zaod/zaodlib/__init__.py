"""Zaod OS platform library: package format, manager, sandbox and store tools."""

__version__ = "0.7.0"

#: Version of the installed Zaod OS image used for ``min_os`` checks when the
#: host has no ``/etc/os-release`` VERSION_ID of its own (for example in tests).
DEFAULT_OS_VERSION = "0.7.0"
