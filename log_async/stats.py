# stat counters for logging handlers

try:
    from prometheus_client import Counter, Gauge
except ImportError:
    # to avoid a forced dependency on prometheus_client,
    # use a super-minimalist implementation of counter.
    # since these are used within same thread, no mutexes are needed.
    class Value:
        def __init__(self, name, desc=''):
            self._name = name
            self._desc = desc
            self._value = 0

        def inc(self, n=1):
            self._value += n

        def dec(self, n=1):
            self._value -= n

        def val(self):
            return (self._name, self._value)

        def reset(self):
            self._value = 0

    class Counter(Value):
        pass

    class Gauge(Value):
        def set(self, n):
            self._value = n


class StatsCollector(object):
    def __init__(self, prefix):
        self._all = []
        self.prefix = prefix

    def get_stats(self):
        return [v.val() for v in self._all]


class TransportStats(StatsCollector):
    def __init__(self, prefix):
        super(TransportStats, self).__init__(prefix)
        self._bytes_sent = Counter(prefix + "sent_bytes", "events received")
        self._errors = Counter(prefix + "errors_total", "socket disconnects")
        self._all.extend([self._bytes_sent, self._errors])

    def socket_error(self):
        self._errors.inc(1)

    def bytes_sent(self, n):
        self._bytes_sent.inc(n)


class LogStats(StatsCollector):

    def __init__(self, prefix):
        super(LogStats, self).__init__(prefix)
        self._events = Counter(prefix + "events_total", "events received")
        self._discarded = Counter(prefix + "discarded_total", "events discarded")
        self._buffered = Gauge(prefix + "buffered_events", "events currently buffered")
        self._sent = Counter(prefix + "sent_total", "events sent to upstream collector")
        self._all.extend([self._events, self._discarded, self._buffered, self._sent])

    def event(self, n=1):
        self._events.inc(n)

    def send(self, n=1):
        self._sent.inc(n)

    def discard(self, n=1):
        self._discarded.inc(n)

    def buffer(self, n=1):
        self._buffered.inc(n)

    def unbuffer(self, n=1):
        self._buffered.dec(min(self._buffered.val()[1], n))


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


class WorkerStats(LogStats):

    def __init__(self, prefix):
        super(WorkerStats, self).__init__(prefix)
        self._queue = Gauge(prefix + "queue_size", "events in queue to process")
        self._all.extend([self._queue, ])

    def set_queue_size(self, val):
        self._queue.set(val)


# lookup - finds stat with s in the name. s should be lower case. Used for testing
def lookup(stats, s):
    for (k, v) in stats:
        if k.lower().find(s) != -1:
            return v
