# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

from datetime import datetime
from logging import getLogger as get_logger
from threading import Event, Thread

from limits import parse as parse_rate_limit
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from six import integer_types
from six.moves.queue import Empty, Queue

from .constants import constants
from .database import DatabaseLockedError
from .stats import WorkerStats
from .utils import safe_log_via_print


class ProcessingError(Exception):
    """"""


class LogProcessingWorker(Thread):
    """"""

    # ----------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        self._host = kwargs.pop('host')
        self._port = kwargs.pop('port')
        self._transport = kwargs.pop('transport')
        self._ssl_enable = kwargs.pop('ssl_enable')
        self._ssl_verify = kwargs.pop('ssl_verify')
        self._keyfile = kwargs.pop('keyfile')
        self._certfile = kwargs.pop('certfile')
        self._ca_certs = kwargs.pop('ca_certs')
        self._database = kwargs.pop('buffer')

        super(LogProcessingWorker, self).__init__(*args, **kwargs)
        self.daemon = True
        self.name = self.__class__.__name__

        self._shutdown_event = Event()
        self._flush_event = Event()
        self._queue = Queue()

        self._event = None
        self._last_event_flush_date = None
        self._non_flushed_event_count = None
        self._logger = None
        self._rate_limit_storage = None
        self._rate_limit_strategy = None
        self._rate_limit_item = None

        self._stats = WorkerStats(constants.WORKER_STATS_PREFIX)

    # ----------------------------------------------------------------------
    def enqueue_event(self, event):
        # called from other threads
        self._stats.event()
        self._queue.put(event)

    # ----------------------------------------------------------------------
    def shutdown(self):
        # called from other threads
        self._shutdown_event.set()

    # ----------------------------------------------------------------------
    def run(self):
        self._reset_flush_counters()
        self._setup_logger()
        try:
            self._fetch_events()
        except Exception as e:
            # we really should not get anything here, and if, the worker thread is dying
            # too early resulting in undefined application behaviour
            self._log_general_error(e)
        # check for empty queue and report if not
        self._warn_about_non_empty_queue_on_shutdown()

    # ----------------------------------------------------------------------
    def get_stats(self):
        self._stats.set_queue_size(self._queue.qsize())
        return self._stats.get_stats()

    # ----------------------------------------------------------------------
    def force_flush_queued_events(self):
        self._flush_event.set()

    # ----------------------------------------------------------------------
    def _reset_flush_counters(self):
        self._last_event_flush_date = datetime.now()
        self._non_flushed_event_count = 0

    # ----------------------------------------------------------------------
    def _clear_flush_event(self):
        self._flush_event.clear()

    # ----------------------------------------------------------------------
    def _setup_logger(self):
        self._logger = get_logger(self.name)
        # rate limit our own messages to not spam around in case of temporary network errors, etc
        rate_limit_setting = constants.ERROR_LOG_RATE_LIMIT
        if rate_limit_setting:
            self._rate_limit_storage = MemoryStorage()
            self._rate_limit_strategy = FixedWindowRateLimiter(self._rate_limit_storage)
            self._rate_limit_item = parse_rate_limit(rate_limit_setting)

    # ----------------------------------------------------------------------
    def _fetch_events(self):
        while True:
            try:
                self._fetch_event()
                self._process_event()
            except Empty:
                # Flush queued (in database) events after internally queued events has been
                # processed, i.e. the queue is empty.
                if self._shutdown_requested():
                    self._flush_queued_events(force=True)
                    return

                force_flush = self._flush_requested()
                self._flush_queued_events(force=force_flush)
                self._delay_processing()
                self._expire_events()
            except (DatabaseLockedError, ProcessingError):
                if self._shutdown_requested():
                    return
                else:
                    self._requeue_event()
                    self._delay_processing()

    # ----------------------------------------------------------------------
    def _fetch_event(self):
        self._event = self._queue.get(block=False)

    # ----------------------------------------------------------------------
    def _process_event(self):
        try:
            self._write_event_to_database()
        except DatabaseLockedError as e:
            self._safe_log(
                u'debug',
                u'Database is locked, will try again later (queue length %d)',
                self._queue.qsize(),
                exc=e)
            raise
        except Exception as e:
            self._log_processing_error(e)
            raise ProcessingError()
        else:
            self._event = None

    # ----------------------------------------------------------------------
    def _expire_events(self):
        try:
            self._database.expire_events()
        except DatabaseLockedError:
            # Nothing to handle, if it fails, we will either successfully publish
            # these messages next time or we will delete them on the next pass.
            pass

    # ----------------------------------------------------------------------
    def _log_processing_error(self, exception):
        self._safe_log(
            u'exception',
            u'Log processing error (queue size: %3s): %s',
            self._queue.qsize(),
            exception,
            exc=exception)

    # ----------------------------------------------------------------------
    def _delay_processing(self):
        self._shutdown_event.wait(constants.QUEUE_CHECK_INTERVAL)

    # ----------------------------------------------------------------------
    def _shutdown_requested(self):
        return self._shutdown_event.is_set()

    # ----------------------------------------------------------------------
    def _flush_requested(self):
        return self._flush_event.is_set()

    # ----------------------------------------------------------------------
    def _requeue_event(self):
        self._queue.put(self._event)

    # ----------------------------------------------------------------------
    def _write_event_to_database(self):
        self._database.add_event(self._event)
        self._non_flushed_event_count += 1

    # ----------------------------------------------------------------------
    def _flush_queued_events(self, force=False):
        # check if necessary and abort if not
        if not force and not self._queued_event_interval_reached() and \
                not self._queued_event_count_reached():
            return

        self._clear_flush_event()

        try:
            queued_events = self._database.get_queued_events()
        except DatabaseLockedError as e:
            self._safe_log(
                u'debug',
                u'Database is locked, will try again later (queue length %d)',
                self._queue.qsize(),
                exc=e)
            return  # try again later
        except Exception as e:
            # just log the exception and hope we can recover from the error
            self._safe_log(u'exception', u'Error retrieving queued events: %s', e, exc=e)
            return

        if queued_events:
            try:
                events = [event['event_text'] for event in queued_events]
                self._send_events(events)
            except Exception as e:
                self._safe_log(
                    u'exception',
                    u'An error occurred while sending events: %s',
                    e,
                    exc=e)
                self._database.requeue_queued_events(queued_events)
            else:
                self._delete_queued_events_from_database()
                self._reset_flush_counters()

    # ----------------------------------------------------------------------
    def _delete_queued_events_from_database(self):
        try:
            self._database.delete_queued_events()
        except DatabaseLockedError:
            pass  # nothing to handle, if it fails, we delete those events in a later run

    # ----------------------------------------------------------------------
    def _queued_event_interval_reached(self):
        delta = datetime.now() - self._last_event_flush_date
        return delta.total_seconds() > constants.QUEUED_EVENTS_FLUSH_INTERVAL

    # ----------------------------------------------------------------------
    def _queued_event_count_reached(self):
        return self._non_flushed_event_count > constants.QUEUED_EVENTS_FLUSH_COUNT

    # ----------------------------------------------------------------------
    def _send_events(self, events):
        self._transport.send(events)
        self._stats.sent(len(events))

    # ----------------------------------------------------------------------
    def _log_general_error(self, exc):
        self._safe_log(u'exception', u'An unexpected error occurred: %s', exc, exc=exc)

    # ----------------------------------------------------------------------
    def _safe_log(self, log_level, message, *args, **kwargs):
        # we cannot log via the logging subsystem any longer once it has been set to shutdown
        if self._shutdown_requested():
            safe_log_via_print(log_level, message, *args, **kwargs)
        else:
            rate_limit_allowed = self._rate_limit_check(kwargs)
            if rate_limit_allowed <= 0:
                return  # skip further logging due to rate limiting
            elif rate_limit_allowed == 1:
                # extend the message to indicate future rate limiting
                message = \
                    u'{} (rate limiting effective, ' \
                    'further equal messages will be limited)'.format(message)

            self._safe_log_impl(log_level, message, *args, **kwargs)

    # ----------------------------------------------------------------------
    def _rate_limit_check(self, kwargs):
        exc = kwargs.pop('exc', None)
        if self._rate_limit_strategy is not None and exc is not None:
            key = self._factor_rate_limit_key(exc)
            # query curent counter for the caller
            _, remaining = self._rate_limit_strategy.get_window_stats(self._rate_limit_item, key)
            # increase the rate limit counter for the key
            self._rate_limit_strategy.hit(self._rate_limit_item, key)
            return remaining

        return 2  # any value greater than 1 means allowed

    # ----------------------------------------------------------------------
    def _factor_rate_limit_key(self, exc):
        module_name = getattr(exc, '__module__', '__no_module__')
        class_name = exc.__class__.__name__
        key_items = [module_name, class_name]
        if hasattr(exc, 'errno') and isinstance(exc.errno, integer_types):
            # in case of socket.error, include the errno as rate limiting key
            key_items.append(str(exc.errno))
        return '.'.join(key_items)

    # ----------------------------------------------------------------------
    def _safe_log_impl(self, log_level, message, *args, **kwargs):
        log_func = getattr(self._logger, log_level)
        log_func(message, *args, **kwargs)

    # ----------------------------------------------------------------------
    def _warn_about_non_empty_queue_on_shutdown(self):
        queue_size = self._queue.qsize()
        if queue_size:
            self._safe_log(
                'warn',
                u'Non-empty queue while shutting down ({} events pending). '
                u'This indicates a previous error.'.format(queue_size),
                extra=dict(queue_size=queue_size))