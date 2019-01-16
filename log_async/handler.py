# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

from logging import Handler

from six import PY2, PY3, string_types, text_type

from .database import DatabaseCache
from .formatter import LogstashFormatter
from .memory_cache import MemoryCache
from .utils import import_string, safe_log_via_print
from .worker import LogProcessingWorker


_default_terminator = PY2 and '\n' or b'\n'


class ProcessingError(Exception):
    """"""


class AsynchronousLogHandler(Handler):
    """Python logging handler for asynchronous log forwarding. Sends events over TCP by default.
    :param host: The host of the log forwarding server, required.
    :param port: The port of the log forwarding server, required.
    :param database_path: The path to the file containing queued events
                          Use None to use a in-memory cache.
                          (database_path is deprecated - use buffer instead.)
    :param transport: Callable or path to a compatible transport class.
    :param ssl_enable: Should SSL be enabled for the connection? Default is False.
    :param ssl_verify: Should the server's SSL certificate be verified?
    :param keyfile: The path to client side SSL key file (default is None).
    :param certfile: The path to client side SSL certificate file (default is None).
    :param ca_certs: The path to the file containing recognized CA certificates.
    :param enable: Flag to enable log processing (default is True, disabling
                   might be handy for local testing, etc.)
    :param event_ttl: Amount of time in seconds to wait before expiring log messages in
                      the database. (Given in seconds. Default is None, and disables this feature)
                      Deprecated - see buffer, below
    :param formatter: Formatter to turn event into byte array (in PY2, into a string)
    :param delimeter: Delimiter to be sent after each message
    :param buffer: Implementation of log_async.Cache
    """

    _worker_thread = None

    # ----------------------------------------------------------------------
    def __init__(self, host, port, database_path=None, transport='log_async.transport.TcpTransport',
                 ssl_enable=False, ssl_verify=True, keyfile=None, certfile=None, ca_certs=None,
                 enable=True, event_ttl=None, encoding='utf-8',
                 formatter=None, buffer=None, terminator=_default_terminator):
        super(AsynchronousLogHandler, self).__init__()
        self._host = host
        self._port = port
        self._database_path = database_path
        self._transport_path = transport
        self._ssl_enable = ssl_enable
        self._ssl_verify = ssl_verify
        self._keyfile = keyfile
        self._certfile = certfile
        self._ca_certs = ca_certs
        self._enable = enable
        self._transport = None
        self._event_ttl = event_ttl
        self._encoding = encoding
        self._buffer = buffer
        self._terminator = terminator
        self._setup_transport()
        self._setup_buffer()
        self._setup_formatter(formatter)

    # ----------------------------------------------------------------------
    def emit(self, record):
        if not self._enable:
            return  # we should not do anything, so just leave

        # create thread on first emit
        # subclasses such as ConsoleLogger may override emit to prevent asynchronous logging
        self._start_worker_thread()

        # basically same implementation as in logging.handlers.SocketHandler.emit()
        try:
            data = self._format_record(record)
            AsynchronousLogHandler._worker_thread.enqueue_event(data)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)

    # ----------------------------------------------------------------------
    def flush(self):
        if self._worker_thread_is_running():
            self._worker_thread.force_flush_queued_events()

    # ----------------------------------------------------------------------
    def _setup_transport(self):
        if self._transport is not None:
            return

        if isinstance(self._transport_path, string_types):
            transport_class = import_string(self._transport_path)
            self._transport = transport_class(
                host=self._host,
                port=self._port,
                ssl_enable=self._ssl_enable,
                ssl_verify=self._ssl_verify,
                keyfile=self._keyfile,
                certfile=self._certfile,
                ca_certs=self._ca_certs)
        else:
            self._transport = self._transport_path

    def _setup_buffer(self):
        if self._buffer is not None:
            return

        # support previous invocation parameters
        if self._database_path:
            self._buffer = DatabaseCache(path=self._database_path, event_ttl=self._event_ttl)
        else:
            self._buffer = MemoryCache(cache={}, event_ttl=self._event_ttl)

    # ----------------------------------------------------------------------
    def _start_worker_thread(self):
        if self._worker_thread_is_running():
            return

        AsynchronousLogHandler._worker_thread = LogProcessingWorker(
            host=self._host,
            port=self._port,
            transport=self._transport,
            ssl_enable=self._ssl_enable,
            ssl_verify=self._ssl_verify,
            keyfile=self._keyfile,
            certfile=self._certfile,
            ca_certs=self._ca_certs,
            buffer=self._buffer)
        AsynchronousLogHandler._worker_thread.start()

    # ----------------------------------------------------------------------
    @staticmethod
    def _worker_thread_is_running():
        worker_thread = AsynchronousLogHandler._worker_thread
        if worker_thread is not None and worker_thread.is_alive():
            return True

    # ----------------------------------------------------------------------
    def _format_record(self, record):
        formatted = self.formatter.format(record)
        if PY3 and isinstance(formatted, text_type):
            formatted = formatted.encode(self._encoding)
        if len(self._terminator):
            formatted = formatted + self._terminator
        return formatted

    # ----------------------------------------------------------------------
    # establish log message formatter, or a LogstashFormatter if one was not provided
    def _setup_formatter(self, formatter):
        if formatter is not None:
            self.formatter = formatter
        elif self.formatter is None:
            self.formatter = LogstashFormatter()

    # ----------------------------------------------------------------------
    def close(self):
        self.acquire()
        try:
            self.shutdown()
        finally:
            self.release()
        super(AsynchronousLogHandler, self).close()

    # ----------------------------------------------------------------------
    def shutdown(self):
        if self._worker_thread_is_running():
            self._trigger_worker_shutdown()
            self._wait_for_worker_thread()
            self._reset_worker_thread()
            self._close_transport()
        else:
            pass

    # ----------------------------------------------------------------------
    def _trigger_worker_shutdown(self):
        AsynchronousLogHandler._worker_thread.shutdown()

    # ----------------------------------------------------------------------
    def _wait_for_worker_thread(self):
        AsynchronousLogHandler._worker_thread.join()

    # ----------------------------------------------------------------------
    def _reset_worker_thread(self):
        AsynchronousLogHandler._worker_thread = None

    # ----------------------------------------------------------------------
    def _close_transport(self):
        try:
            if self._transport is not None:
                self._transport.close()
        except Exception as e:
            safe_log_via_print('error', u'Error on closing transport: {}'.format(e))

    # ----------------------------------------------------------------------
    def get_stats(self):
        vals = []
        if self._enable:
            if AsynchronousLogHandler._worker_thread:
                vals.extend(AsynchronousLogHandler._worker_thread.get_stats())
            if self._transport is not None:
                vals.extend(self._transport.get_stats())
            if self._buffer is not None:
                vals.extend(self._buffer.get_stats())
        return vals
