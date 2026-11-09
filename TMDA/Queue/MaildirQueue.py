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

"""Maildir compatible pending queue format.

http://en.wikipedia.org/wiki/Maildir
"""


from email.utils import parseaddr
from glob import glob


import fcntl
import os
import socket
import stat
import tempfile
import time


from TMDA import Defaults
from TMDA import Errors
from TMDA import Util
from TMDA.Queue.Queue import Queue, validate_mailid


def alarm_handler(signum, frame):
    """Handle an alarm."""
    print(('Signal handler called with signal', signum))
    raise IOError("Couldn't open device!")

def lock_file(fp):
    """Do fcntl file locking."""
    fcntl.flock(fp.fileno(), fcntl.LOCK_EX)

def unlock_file(fp):
    """Do fcntl file unlocking."""
    fcntl.flock(fp.fileno(), fcntl.LOCK_UN)



class MaildirQueue(Queue):
    def __init__(self):
        Queue.__init__(self)
        self.format = "maildir"


    def exists(self):
        if os.path.exists(Defaults.PENDING_DIR):
            return True
        else:
            return False


    def _create(self):
        dirpath = Defaults.PENDING_DIR
        for dirname in ('cur', 'new', 'tmp'):
            os.makedirs(os.path.join(dirpath, dirname), mode=0o700,
                        exist_ok=True)


    def _convert(self):
        pass


    def cleanup(self):
        if not self.exists():
            return
        
        lifetimesecs = Util.seconds(Defaults.PENDING_LIFETIME)
        msgs = self._messages()

        for msg in msgs:
            now = '%d' % time.time()
            min_time = int(now) - int(lifetimesecs)
            msg_time = int(os.path.basename(msg).split('.')[0])
            if msg_time > min_time:
                # skip this message
                continue
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
        ids = ['.'.join(os.path.basename(path).split('.')[:2])
               for path in self._messages()]
        return ids


    def insert_message(self, msg, mailid, recipient):
        validate_mailid(mailid)
        self._create()
        original_headers = msg.get_all('X-TMDA-Recipient', [])
        try:
            del msg['X-TMDA-Recipient']
            msg['X-TMDA-Recipient'] = recipient
            timestamp, pid = mailid.split('.')
            self.__deliver_maildir(Util.msg_as_string(msg), timestamp, pid,
                                   Defaults.PENDING_DIR)
        finally:
            del msg['X-TMDA-Recipient']
            for value in original_headers:
                msg['X-TMDA-Recipient'] = value


    def _messages(self):
        """Return pending Maildir messages in the new and cur directories."""
        return (glob(os.path.join(Defaults.PENDING_DIR, 'new', '1*.[0-9]*.*')) +
                glob(os.path.join(Defaults.PENDING_DIR, 'cur', '1*.[0-9]*.*')))

    def _matching_messages(self, mailid):
        validate_mailid(mailid)
        """Match the complete mail identifier, not an arbitrary substring."""
        prefix = mailid + '.'
        return [path for path in self._messages()
                if os.path.basename(path).startswith(prefix)]

    def fetch_message(self, mailid, fullParse=False):
        for path in self._matching_messages(mailid):
            with open(path, 'r', encoding='latin-1') as fp:
                return Util.msg_from_file(fp, fullParse=fullParse)
        raise IOError("couldn't locate %s, will retry" % mailid)


    def delete_message(self, mailid):
        for path in self._matching_messages(mailid):
            os.unlink(path)


    def find_message(self, mailid):
        for attempt in range(5):
            if self._matching_messages(mailid):
                return True
            # Retry in case a mail client is moving new/ to cur/.
            if attempt < 4:
                time.sleep(0.1)
        return False


    def __deliver_maildir(self, message, time, pid, maildir):
        """Atomically publish a complete message in Maildir/new.

        A private temporary filename prevents concurrent writers from
        corrupting the same queue identifier. Publishing via os.link()
        refuses to overwrite a message already present.
        """
        filename = '%s.%s.%s' % (time, pid, socket.gethostname())
        dir_tmp = os.path.join(maildir, 'tmp')
        dir_cur = os.path.join(maildir, 'cur')
        dir_new = os.path.join(maildir, 'new')
        if not all(os.path.isdir(path) for path in
                   (dir_tmp, dir_cur, dir_new)):
            raise Errors.DeliveryError('not a Maildir! (%s)' % maildir)

        fname_new = os.path.join(dir_new, filename)
        fname_cur = os.path.join(dir_cur, filename)
        if os.path.exists(fname_new) or os.path.exists(fname_cur):
            raise Errors.DeliveryError('pending message already exists: %s'
                                       % filename)

        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(
                prefix='.tmda-', suffix='.tmp', dir=dir_tmp)
            owner = os.stat(maildir)
            with os.fdopen(fd, 'wb') as fp:
                try:
                    os.fchown(fp.fileno(), owner.st_uid, owner.st_gid)
                except PermissionError:
                    pass
                if isinstance(message, str):
                    message = message.encode('latin-1')
                fp.write(message)
                fp.flush()
                os.fsync(fp.fileno())
            os.link(temporary, fname_new)
        except (OSError, IOError) as error:
            raise Errors.DeliveryError(
                'Failure publishing Maildir message %s (%s)' %
                (filename, error)) from error
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
