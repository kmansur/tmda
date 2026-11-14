# -*- python -*-
#
# This file is part of TMDA and is distributed under the same
# GPL-2.0-or-later license as the original project.
#
"""Compatibility binding for the Unix crypt(3) function.

Python 3.13 removed the stdlib crypt module.  Use the operating system's
crypt(3) function to preserve the legacy password-file authentication
format without changing algorithms or adding password hashing features.
"""

import ctypes
import ctypes.util


def crypt(password, salt):
    """Return the system crypt(3) hash as an ASCII string, or None."""
    if isinstance(password, str):
        password = password.encode("latin-1")
    if isinstance(salt, str):
        salt = salt.encode("latin-1")

    # FreeBSD normally exposes crypt(3) through libcrypt or libc;
    # Linux systems generally expose it through libcrypt.
    candidates = (ctypes.util.find_library("crypt"),
                  ctypes.util.find_library("c"), None)
    for library in candidates:
        try:
            handle = ctypes.CDLL(library)
            native_crypt = handle.crypt
        except (OSError, AttributeError):
            continue

        native_crypt.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
        native_crypt.restype = ctypes.c_char_p
        result = native_crypt(password, salt)
        return result.decode("ascii") if result is not None else None

    raise OSError("The operating system does not provide crypt(3)")
