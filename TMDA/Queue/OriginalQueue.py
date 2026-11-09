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

"""Original pending queue format.  

The original style TMDA queue is the only option one had under TMDA
1.0.x and early 1.1.x releases. It's simply a single directory of
files, one mail message stored per file, where files are named
"mailid.msg" (e.g, 1159377144.3747.msg).  It almost looks like a
Maildir without subdirectories.  It perhaps offers the best
performance, but since it's a custom format, it can't be accessed and
read with non-TMDA tools so may not be as convenient for users who
wish to monitor the contents of their pending queue.
"""


from email.utils import parseaddr

import glob
import os
import tempfile
import time

from TMDA import Defaults
from TMDA import Util
from TMDA.Queue.Queue import Queue, validate_mailid



class OriginalQueue(Queue):
    def __init__(self):
        Queue.__init__(self)
        self.format = "original"


    def exists(self):
        if os.path.exists(Defaults.PENDING_DIR):
            return True
        else:
            return False


    def _create(self):
        if not self.exists():
            os.makedirs(Defaults.PENDING_DIR, 0o700)


    def _convert(self):
        pass


    def cleanup(self):
        if not self.exists():
            return
        
        lifetimesecs = Util.seconds(Defaults.PENDING_LIFETIME)
        msgs = glob.glob(os.path.join(Defaults.PENDING_DIR, '*.*.msg'))

        for msg in msgs:
            now = '%d' % time.time()
            min_time = int(now) - int(lifetimesecs)
            msg_time = int(os.path.basename(msg).split('.')[0])
            if msg_time > min_time:
                # skip this message
                continue
            # delete this message
            fpath = msg
            if Defaults.PENDING_DELETE_APPEND:
                try:
                    with open(fpath, 'r', encoding='latin-1') as fp:
                        msgobj = Util.msg_from_file(fp)
                except IOError:
                    # in case of concurrent cleanups
                    pass
                else:
                    rp = parseaddr(msgobj.get('return-path'))[1]
                    Util.append_to_file(rp, Defaults.PENDING_DELETE_APPEND)
            try:
                os.unlink(fpath)
            except OSError:
                # in case of concurrent cleanups
                pass


    def fetch_ids(self):
        msgs = glob.glob(os.path.join(Defaults.PENDING_DIR, '*.*.msg'))
        return [os.path.basename(path)[:-4] for path in msgs]


    def insert_message(self, msg, mailid, recipient):
        """Atomically publish a fully written message under its legacy ID."""
        validate_mailid(mailid)
        self._create()
        fpath = os.path.join(Defaults.PENDING_DIR, mailid + '.msg')
        original_headers = msg.get_all('X-TMDA-Recipient', [])
        temporary = None
        try:
            del msg['X-TMDA-Recipient']
            msg['X-TMDA-Recipient'] = recipient
            contents = Util.msg_as_string(msg)
            if isinstance(contents, str):
                contents = contents.encode('latin-1')
            fd, temporary = tempfile.mkstemp(
                prefix='.tmda-', suffix='.tmp', dir=Defaults.PENDING_DIR)
            with os.fdopen(fd, 'wb') as fp:
                fp.write(contents)
                fp.flush()
                os.fsync(fp.fileno())
            # Hard-link creation refuses an existing destination. Readers
            # never observe a partially written *.msg file.
            os.link(temporary, fpath)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            del msg['X-TMDA-Recipient']
            for value in original_headers:
                msg['X-TMDA-Recipient'] = value


    def fetch_message(self, mailid, fullParse=False):
        validate_mailid(mailid)
        fpath = os.path.join(Defaults.PENDING_DIR, mailid + '.msg')
        with open(fpath, 'r', encoding='latin-1') as fp:
            return Util.msg_from_file(fp, fullParse=fullParse)


    def delete_message(self, mailid):
        validate_mailid(mailid)
        fpath = os.path.join(Defaults.PENDING_DIR, mailid + '.msg')
        os.unlink(fpath)


    def find_message(self, mailid):
        validate_mailid(mailid)
        fpath = os.path.join(Defaults.PENDING_DIR, mailid + '.msg')
        if os.path.exists(fpath):
            return True
        else:
            return False
