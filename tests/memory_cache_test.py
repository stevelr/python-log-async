# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

import unittest
import datetime

from log_async.memory_cache import MemoryCache
from log_async.stats import lookup


class MemoryCacheTest(unittest.TestCase):

    # ----------------------------------------------------------------------
    def test_add_event(self):
        cache = MemoryCache({})
        cache.add_event("message")
        self.assertEqual(len(cache._cache), 1)
        event = list(cache._cache.values())[0]
        self.assertEqual(event['event_text'], 'message')
        self.assertEqual(event['pending_delete'], False)

    # ----------------------------------------------------------------------
    def test_get_queued_events(self):
        cache = MemoryCache({
            "id1": {"pending_delete": True},
            "id2": {"pending_delete": False}
        })
        self.assertEqual(len(cache.get_queued_events()), 1)

    # ----------------------------------------------------------------------
    def test_get_queued_events_pending_delete_check(self):
        cache = MemoryCache({
            "id1": {"pending_delete": False}
        })
        queued_events = cache.get_queued_events()
        self.assertEqual(len(queued_events), 1)
        self.assertTrue(queued_events[0])

    # ----------------------------------------------------------------------
    def test_requeue_queued_events(self):
        cache = MemoryCache({
            "id1": {"pending_delete": True}
        })
        self.assertEqual(len(cache.get_queued_events()), 0)
        cache.requeue_queued_events([{"id": "id1"}])
        self.assertEqual(len(cache.get_queued_events()), 1)

    # ----------------------------------------------------------------------
    def test_delete_queued_events(self):
        cache = MemoryCache({
            "id1": {"pending_delete": True, "id": "id1"},
            "id2": {"pending_delete": False, "id": "id2"}
        })
        cache.delete_queued_events()
        self.assertEqual(len(cache._cache), 1)

    # ----------------------------------------------------------------------
    def test_expire_events(self):
        cache = MemoryCache({
            "id1": {"pending_delete": False, "id": "id1", "entry_date": datetime.datetime.fromtimestamp(0)},
            "id2": {"pending_delete": False, "id": "id2", "entry_date": datetime.datetime.now()}
        }, event_ttl=100)
        cache.expire_events()
        self.assertEqual(len(cache._cache), 1)

    # ----------------------------------------------------------------------
    def test_event_counter(self):
        cache = MemoryCache({})
        cache.add_event("message")
        e1 = lookup(cache.get_stats(), 'events_total')
        self.assertEqual(1, e1)
        b1 = lookup(cache.get_stats(), 'buffered')
        self.assertEqual(1, b1)
        cache.get_queued_events()
        cache.delete_queued_events()
        b2 = lookup(cache.get_stats(), 'buffered')
        self.assertEqual(0, b2)
