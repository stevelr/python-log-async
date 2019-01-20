# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

from contextlib import contextmanager
import os
import sqlite3
import sys

import six

from .cache import Cache
from .constants import constants
from .stats import Counter, Gauge, LogStats
from .utils import ichunked


DATABASE_SCHEMA_STATEMENTS = [
    '''
    CREATE TABLE IF NOT EXISTS `event` (
    `event_id`          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    `event_text`        TEXT NOT NULL,
    `pending_delete`    INTEGER NOT NULL,
    `entry_date`        TEXT NOT NULL);
    ''',
    '''CREATE INDEX IF NOT EXISTS `idx_pending_delete` ON `event` (pending_delete);''',
    '''CREATE INDEX IF NOT EXISTS `idx_entry_date` ON `event` (entry_date);''',
]


class DatabaseStats(LogStats):

    def __init__(self, prefix):
        super(DatabaseStats, self).__init__(prefix)
        self._fsize = Gauge(prefix + "file_bytes", "size of sqlite file")
        self._lock_errors = Counter(prefix + "lock_errors_total",
                                    "number of database lock conflicts encountered")
        self._all.extend([self._fsize, self._lock_errors])

    def set_file_size(self, nbytes):
        self._fsize.set(nbytes)

    def lock_error(self):
        self._lock_errors.inc(1)


class DatabaseLockedError(Exception):
    pass


class DatabaseCache(Cache):
    """
        Backend implementation for python-log-async. Keeps messages on disk in a SQL-lite DB
        while attempting to publish them to log forwarder. Persists log messages through restarts
        of a process.

        :param path: Path to the SQLite database
        :param event_ttl: Optional parameter used to expire events in the database after a time
        :param max_size: maximum number of buffered events, excluding events saved on prior runs
        :param overflow_fn: Function to call in case of overflow. Important - don't just log to
                the same path or there could be an infinite loop!
    """

    # ----------------------------------------------------------------------
    def __init__(self, path, event_ttl=None, max_size=None, overflow_fn=None):
        self._database_path = path
        self._connection = None
        self._event_ttl = event_ttl
        self._max_size = max_size
        self._overflow_fn = overflow_fn
        self._stats = DatabaseStats(constants.DATABASE_STATS_PREFIX)

    @contextmanager
    def _connect(self):
        self._open()
        try:
            with self._connection as connection:
                yield connection
        except sqlite3.OperationalError:
            self._handle_sqlite_error()
            raise
        finally:
            self._close()

    # ----------------------------------------------------------------------
    def _open(self):
        self._connection = sqlite3.connect(
            self._database_path,
            timeout=constants.DATABASE_TIMEOUT,
            isolation_level='EXCLUSIVE')
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    # ----------------------------------------------------------------------
    def _close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ----------------------------------------------------------------------
    def _initialize_schema(self):
        cursor = self._connection.cursor()
        try:
            for statement in DATABASE_SCHEMA_STATEMENTS:
                cursor.execute(statement)
        except sqlite3.OperationalError:
            self._close()
            self._handle_sqlite_error()
            raise

    # ----------------------------------------------------------------------
    def add_event(self, event):
        self._stats.event(1)
        if self._max_size is not None and self._stats.totalBuffered() >= self._max_size:
            self._stats.discard(1)
            if self._overflow_fn:
                try:
                    self._overflow_fn(event)
                except Exception:
                    pass
            return

        query = u'''
            INSERT INTO `event`
            (`event_text`, `pending_delete`, `entry_date`) VALUES (?, ?, datetime('now'))'''
        with self._connect() as connection:
            connection.execute(query, (event, False))
        self._stats.buffer(1)

    def get_stats(self):
        try:
            fsize = os.stat(self._database_path).st_size
            self._stats.set_file_size(fsize)
        except Exception:
            # if we database_path is invalid, we've already received an error
            # if we can't get the file size, something is seriously wrong with fs
            # and should have been logged already. Either way, to avoid
            # infinite recursion, we can't log more errors if logging is failing
            pass
        return self._stats.get_stats()

    # ----------------------------------------------------------------------
    def _handle_sqlite_error(self):
        _, e, traceback = sys.exc_info()
        if str(e) == 'database is locked':
            self._stats.lock_error()
            six.reraise(DatabaseLockedError, DatabaseLockedError(e), traceback)

    # ----------------------------------------------------------------------
    def get_queued_events(self):
        query_fetch = 'SELECT `event_id`, `event_text` FROM `event` WHERE `pending_delete` = 0;'
        query_update_base = 'UPDATE `event` SET `pending_delete`=1 WHERE `event_id` IN (%s);'
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query_fetch)
            events = cursor.fetchall()
            self._bulk_update_events(cursor, events, query_update_base)
        self._stats.unbuffer(len(events))
        return events

    # ----------------------------------------------------------------------
    def _bulk_update_events(self, cursor, events, statement_base):
        event_ids = [event[0] for event in events]
        # split into multiple queries as SQLite has a maximum 1000 variables per query
        numRows = 0
        for event_ids_subset in ichunked(event_ids, constants.DATABASE_EVENT_CHUNK_SIZE):
            statement = statement_base % ','.join('?' * len(event_ids_subset))
            cursor.execute(statement, event_ids_subset)
            numRows += cursor.rowcount
        return numRows

    # ----------------------------------------------------------------------
    def requeue_queued_events(self, events):
        query_update_base = 'UPDATE `event` SET `pending_delete`=0 WHERE `event_id` IN (%s);'
        with self._connect() as connection:
            cursor = connection.cursor()
            n = self._bulk_update_events(cursor, events, query_update_base)
            if n > 0:
                self._stats.buffer(n)

    # ----------------------------------------------------------------------
    def delete_queued_events(self):
        query_delete = 'DELETE FROM `event` WHERE `pending_delete`=1;'
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query_delete)

    # ----------------------------------------------------------------------
    def expire_events(self):
        if self._event_ttl is None:
            return

        query_delete = "DELETE FROM `event` WHERE `entry_date` < datetime('now', '-{} seconds');" \
            .format(self._event_ttl)
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query_delete)
            numDeleted = cursor.rowcount
            if numDeleted > 0:
                self._stats.discard(numDeleted)
