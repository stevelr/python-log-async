Configuration
-------------

Options for configuring the log handler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``host``

    The host of the Log forwarding server

    *Type*: ``string``

    *Default*: None


``port``

    The port of the Log forwarding server

    *Type*: ``integer``

    *Default*: None


``database_path``

    The path to the file containing queued events.
    To use an in-memory cache instead of a SQLite database,
    simply pass ``None``. See :doc:`persistence` for details.

    *Type*: ``string``

    *Default*: None


``transport``
    Callable or path to a compatible transport class.

    You can specify your own transport class, e.g. to implement
    a transport via Redis or the Beats protocol.
    If you support pass a string, it should be a path to a
    class which can be imported.
    If you pass anything else, it should be an object of a class
    with a similar interface as `log_async.transport.TcpTransport`.
    Especially it should provide a `close()` and a `send()` method.

    *Type*: ``string``

    *Default*: ``log_async.transport.TcpTransport``


``ssl_enable``

    Should SSL be enabled for the connection?
    Only used for `log_async.transport.TcpTransport`.

    *Type*: ``boolean``

    *Default*: ``False``


``ssl_verify``

    Should the server's SSL certificate be verified?
    Only used for `log_async.transport.TcpTransport`.

    *Type*: ``boolean``

    *Default*: ``True``


``keyfile``

    The path to client side SSL key file.
    Only used for `log_async.transport.TcpTransport`.

    *Type*: ``string``

    *Default*: None


``certfile``

    The path to client side SSL certificate file.
    Only used for `log_async.transport.TcpTransport`.

    *Type*: ``string``

    *Default*: None


``ca_certs``

    The path to the file containing recognized CA certificates.
    Only used for `log_async.transport.TcpTransport`.

    *Type*: ``string``

    *Default*: None


``enable``

    Flag to enable log processing (disabling might be handy for
    local testing, etc.)

    *Type*: ``boolean``

    *Default*: True


``event_ttl``

    TTL for messages that are waiting to be published.
    If a message is beyond it's TTL, it will be deleted from the cache
    and will not be published to the logging server.

    *Type*: ``integer``

    *Default*: None



Options for configuring the log formatter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following settings are only valid for the provided formatters
`log_async.handler.LogstashFormatter` and
`log_async.handler.DjangoLogstashFormatter`.

You can use any other formatter by configuring Python's logging
system accordingly. Any other formatter's `format()` method just
should return valid JSON suitable to be sent to the logging server
(see :ref:`log-async-config`).

Options:

``message_type``

    The `type` field in the message sent to Logstash

    *Type*: ``string``

    *Default*: ``python-logstash``


``tags``

    Additional tags to include in the Logstash message

    *Type*: ``list``

    *Default*: None


``fqdn``

    Use the system's FQDN (fully qualified domain name) in the `host`
    field of the message sent to Logstash.
    `socket.getfqdn()` is used to retrieve the FQDN, otherwise
    `socket.gethostname()` is used for the default hostname.

    *Type*: ``boolean``

    *Default*: ``False``


``extra_prefix``

    Name of the field in the resulting message sent to Logstash where
    all additional fields are grouped into. Consider it as some sort
    of namespace for all non-standard fields in the log event.
    This field will take any items passed in as extra fields via
    the `extra` configuration option (see below) as well as any extra
    items passed in the logging call.

    To disable grouping of the extra items and have them on the top
    level of the log event message, simply set this option to `None`
    or the empty string.

    *Type*: ``string``

    *Default*: ``extra``


``extra``

    Dictionary with static items to be included in the message sent
    to Logstash. This dictionary will be merged with any other extra
    items passed in the logging call.

    *Type*: ``dict``

    *Default*: None


``ensure_ascii``

    By default non-ASCII symbols in JSON are escaped with \uXXXX
    sequence. But on some specific settings of Elastic Stack
    those sequences won't be transformed back to UTF-8 representation.
    For those specific cases try to set parameter to 'False'.

    *Type*: ``boolean``

    *Default*: ``True``


.. _module-constants:

Options for the asynchronous processing and formatting
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are a few constants which are meant to be static but still can be overridden
from the calling application by importing the ``constants`` variable from the
``logstash_async.constants`` which holds all constants as attributes
for easy modification.


``constants.SOCKET_TIMEOUT``

    Timeout in seconds for TCP connections

    *Type*: ``float``

    *Default*: ``5.0``


``constants.QUEUE_CHECK_INTERVAL``

    Interval in seconds to check the internal queue for new messages
    to be cached in the database

    *Type*: ``float``

    *Default*: ``2.0``


``constants.QUEUED_EVENTS_FLUSH_INTERVAL``

    Interval in seconds to send cached events from the database
    to Logstash

    *Type*: ``float``

    *Default*: ``10.0``


``constants.QUEUED_EVENTS_FLUSH_COUNT``

    Count of cached events to send cached events from the database
    to Logstash; events are sent to Logstash whenever
    `QUEUED_EVENTS_FLUSH_COUNT` or `QUEUED_EVENTS_FLUSH_INTERVAL` is reached,
    whatever happens first

    *Type*: ``integer``

    *Default*: ``50``


``constants.DATABASE_EVENT_CHUNK_SIZE``

    Maximum number of events to be updated within one SQLite statement

    *Type*: ``integer``

    *Default*: ``750``


``constants.DATABASE_TIMEOUT``

    Timeout in seconds to "connect" (i.e. open) the SQLite database

    *Type*: ``float``

    *Default*: ``5.0``


``constants.FORMATTER_RECORD_FIELD_SKIP_LIST``

    List of Python standard LogRecord attributes which are filtered out from the event sent
    to Logstash. Usually this list does not need to be modified. Add/Remove elements to
    exclude/include them in the Logstash event, for the full list see:
    http://docs.python.org/library/logging.html#logrecord-attributes

    *Type*: ``list``

    *Default*: <see source code>


``constants.FORMATTER_LOGSTASH_MESSAGE_FIELD_LIST``

    Fields to be set on the top-level of a Logstash event/message, do not modify this
    unless you know what you are doing

    *Type*: ``list``

    *Default*: <see source code>


``constants.ERROR_LOG_RATE_LIMIT``

    Enable rate limiting for error messages (e.g. network errors) emitted by the logger
    used in LogProcessingWorker, i.e. when transmitting log messages to the Logstash server.
    In case the Logstash cannot be reached due to network issues
    (timeouts, connection refused, ...), this may lead to many repeated error log messages which
    can get annoying, especially if the application's logging system is configured to send emails
    or other notifications. For such errors emitted directly from the LogProcessingWorker class,
    rate limiting of identical errors for some time period can be configured to reduce logging
    of the same errors. In case rate limiting is in effect, the last message before dropping further
    messages will contain a hint telling that further messages of this kind will be dropped.
    To disable set this to `None`, to enable use a string like '5 per minute',
    for details see http://limits.readthedocs.io/en/stable/string-notation.html.

    .. note::
        This rate limit affects only error log messages emitted directly in
        LogProcessingWorker, if you need a general rate limiting of all log messages,
        use a filter for the logging framework, e.g. https://github.com/wkeeling/ratelimitingfilter.

    *Type*: ``string``

    *Default*: None


Example usage:

.. code-block:: python

  from log_async.constants import constants

  constants.SOCKET_TIMEOUT = 10.0

  from log_async.handler import AsynchronousLogHandler
  ...
