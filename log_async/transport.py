# -*- coding: utf-8 -*-
#
# This software may be modified and distributed under the terms
# of the MIT license.  See the LICENSE file for details.

import socket
import ssl
import sys

from log_async.constants import constants
from log_async.stats import Counter, StatsCollector


class TransportStats(StatsCollector):
    def __init__(self, prefix):
        super(TransportStats, self).__init__(prefix)
        self._bytes_sent = Counter(prefix + "sent_bytes", "bytes transmitted")
        self._events_sent = Counter(prefix + "sent_msgs", "events transmitted")
        self._errors = Counter(prefix + "errors_total", "socket disconnects")
        self._all.extend([self._bytes_sent, self._events_sent, self._errors])

    def socket_error(self):
        self._errors.inc(1)

    def bytes_sent(self, n):
        self._bytes_sent.inc(n)

    def events_sent(self, n):
        self._events_sent.inc(n)


class UdpTransport(object):

    _keep_connection = False

    # ----------------------------------------------------------------------
    def __init__(self, host, port, **kwargs):
        self._host = host
        self._port = port
        self._sock = None
        self._stats = TransportStats(constants.TRANSPORT_STATS_PREFIX)

    # ----------------------------------------------------------------------
    def send(self, events):
        # Ideally we would keep the socket open but this is risky because we might not notice
        # a broken TCP connection and send events into the dark.
        # On UDP we push into the dark by design :)
        self._create_socket()
        try:
            self._send(events)
            self._stats.events_sent(len(events))
        except Exception:
            self._stats.socket_error()
            raise
        finally:
            self._close()

    # ----------------------------------------------------------------------
    def _create_socket(self, timeout=constants.SOCKET_TIMEOUT):
        if self._sock is not None:
            return

        # from logging.handlers.DatagramHandler
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(timeout)

    # ----------------------------------------------------------------------
    def _send(self, events):
        for event in events:
            self._send_via_socket(event)

    # ----------------------------------------------------------------------
    def _send_via_socket(self, data):
        data_to_send = self._convert_data_to_send(data)
        self._sock.sendto(data_to_send, (self._host, self._port))
        self._stats.bytes_sent(len(data_to_send))

    # ----------------------------------------------------------------------
    def _convert_data_to_send(self, data):
        if sys.version_info < (3, 0):
            return data
        # Python3
        elif not isinstance(data, bytes):
            return bytes(data, 'utf-8')

        return data

    # ----------------------------------------------------------------------
    def _close(self, force=False):
        if not self._keep_connection or force:
            if self._sock:
                self._sock.close()
                self._sock = None

    # ----------------------------------------------------------------------
    def close(self):
        self._close(force=True)

    # ----------------------------------------------------------------------
    def get_stats(self):
        return self._stats.get_stats()


class TcpTransport(UdpTransport):

    # ----------------------------------------------------------------------
    def __init__(self, host, port, ssl_enable, ssl_verify, keyfile, certfile, ca_certs):
        super(TcpTransport, self).__init__(host, port)
        self._ssl_enable = ssl_enable
        self._ssl_verify = ssl_verify
        self._keyfile = keyfile
        self._certfile = certfile
        self._ca_certs = ca_certs

    # ----------------------------------------------------------------------
    def _create_socket(self, timeout=constants.SOCKET_TIMEOUT):
        if self._sock is not None:
            return

        # from logging.handlers.SocketHandler
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((self._host, self._port))
        # non-SSL
        if not self._ssl_enable:
            self._sock = sock
            return
        # SSL
        cert_reqs = ssl.CERT_REQUIRED
        if not self._ssl_verify:
            if self._ca_certs:
                cert_reqs = ssl.CERT_OPTIONAL
            else:
                cert_reqs = ssl.CERT_NONE
        self._sock = ssl.wrap_socket(
            sock,
            keyfile=self._keyfile,
            certfile=self._certfile,
            ca_certs=self._ca_certs,
            cert_reqs=cert_reqs)

    # ----------------------------------------------------------------------
    def _send_via_socket(self, data):
        data_to_send = self._convert_data_to_send(data)
        self._sock.sendall(data_to_send)
        self._stats.bytes_sent(len(data_to_send))
