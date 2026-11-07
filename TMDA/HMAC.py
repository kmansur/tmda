# -*- python -*-
#
# Copyright (C) 2001-2007 Jason R. Mastaler <jason@mastaler.com>
#
# This file is part of TMDA.
#
# TMDA is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  A copy of this license should
# be included in the file COPYING.
#
# TMDA is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License
# along with TMDA; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

"""
HMAC (Keyed-Hashing for Message Authentication) in Python.

Implements the HMAC algorithm for SHA-1 as described by
RFC 2104 (http://www.faqs.org/rfcs/rfc2104.html).

Python >= 2.2 includes a more general purpose HMAC module
(http://www.python.org/doc/current/lib/module-hmac.html).

Based on code from p2.py
<URL:http://www.nightsong.com/phr/crypto/p2.py>
Copyright (C) 2002 Paul Rubin
"""

import hashlib
import hmac as _hmac


def _as_bytes(value):
    """Convert Python 2 byte strings without changing their contents."""
    if isinstance(value, str):
        return value.encode('latin-1')
    return value


class hmac:
    """Compatibility wrapper for TMDA's original HMAC-SHA1 interface."""

    def __init__(self, k, m=None):
        if isinstance(k, hmac):
            self._context = k._context.copy()
        else:
            self._context = _hmac.new(_as_bytes(k), digestmod=hashlib.sha1)
            if m is not None:
                self.update(m)

    def update(self, m):
        self._context.update(_as_bytes(m))

    def digest(self):
        return self._context.digest()


def new(k, m=None):
    return hmac(k, m)
