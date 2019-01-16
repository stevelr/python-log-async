# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

from datetime import datetime, timedelta
from logging import getLogger as get_logger
import uuid

from .cache import Cache
from .constants import constants
from .stats import LogStats


class MemoryCache(Cache):
    """Backend implementation for python-log-async. Keeps messages in a local, in-memory cache
    while attempting to publish them to the log forwarder.
    Does not persist through process restarts. Also, does not write to disk.

    :param cache: Usually just an empty dictionary
    :param event_ttl: Optional parameter used to expire events in the cache after a time
    :param max_size: maximum number of buffered events
    :param overflow_fn: Function to call in case of overflow. Important - don't just log to
            the same path or there could be an infinite loop!
    """

    logger = get_logger(__name__)

    # ----------------------------------------------------------------------
    def __init__(self, cache, event_ttl=None, max_size=None, overflow_fn=None):
        self._cache = cache
        self._event_ttl = event_ttl
        self._max_size = max_size
        self._overflow_fn = overflow_fn
        self._stats = LogStats(constants.MEMORY_STATS_PREFIX)

    # ----------------------------------------------------------------------
    def add_event(self, event):
        self._stats.event(1)
        if self._max_size is not None and len(self._cache) >= self._max_size:
            self._stats.discard(1)
            if self._overflow_fn:
                try:
                    self._overflow_fn(event)
                except Exception:
                    pass
            return

        event_id = uuid.uuid4()
        self._cache[event_id] = {
            "event_text": event,
            "pending_delete": False,
            "entry_date": datetime.now(),
            "id": event_id
        }
        self._stats.buffer(1)

    # ----------------------------------------------------------------------
    def get_queued_events(self):
        events = []
        for event in self._cache.values():
            if not event['pending_delete']:
                events.append(event)
                event['pending_delete'] = True
        self._stats.unbuffer(len(events))
        return events

    # ----------------------------------------------------------------------
    def requeue_queued_events(self, events):
        n = 0
        for event in events:
            event_to_queue = self._cache.get(event['id'], None)
            # If they gave us an event which is not in the cache,
            # there is really nothing for us to do. Right now
            # this use-case does not raise an error. Instead, we
            # just log the message.
            if event_to_queue:
                event_to_queue['pending_delete'] = False
                n += 1
            else:
                self.logger.warn(
                    "Could not requeue event with id {}. "
                    "It does not appear to be in the cache.".format(event['id']))
        self._stats.buffer(n)

    # ----------------------------------------------------------------------
    def delete_queued_events(self):
        ids_to_delete = [event['id'] for event in self._cache.values() if event['pending_delete']]
        self._delete_events(ids_to_delete)

    # ----------------------------------------------------------------------
    def expire_events(self):
        if self._event_ttl is None:
            return

        delete_time = datetime.now() - timedelta(seconds=self._event_ttl)
        ids_to_delete = [
            event['id']
            for event in self._cache.values()
            if event['entry_date'] < delete_time]
        self._delete_events(ids_to_delete)

    # ----------------------------------------------------------------------
    def _delete_events(self, ids_to_delete):
        n = 0
        for event_id in ids_to_delete:
            # If the event is not in the cache, is there anything
            # that we can do. This currently doesn't throw an error.
            event = self._cache.pop(event_id, None)
            if event:
                n += 1
            else:
                self.logger.warn(
                    "Could not delete event with id {}. "
                    "It does not appear to be in the cache.".format(event_id))
        self._stats.discard(n)

    # ----------------------------------------------------------------------
    def get_stats(self):
        return self._stats.get_stats()
