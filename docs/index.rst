.. python-log-async documentation master file

Python Log Async
================

Python Log Async is an asynchronous Python logging handler to submit
log events to a remote log server or log forwarding server.
It is based on python-logstash-async, with added generalizations
to support logging protocols such as fluentd and google pubsub.
It also integrates well with the eventlog and django-eventlog libraries
for event and metrics reporting.

Unlike some other python asynchronous logging packages, this package works
for both python 2 and 3, and does not have any dependencies on asyncio.

Unlike most other Python Logstash logging handlers, this package works asynchronously
by collecting log events from Python's logging subsystem and then transmitting the
collected events in a separate worker thread to Logstash.
This way, the main application (or thread) where the log event occurred, doesn't need to
wait until the submission to the remote Logstash instance succeeded.

This is especially useful for applications like websites or web services or any kind of
request serving API where response times matter.


Contents
--------

.. toctree::
   :maxdepth: 2

   about.rst
   installation.rst
   usage.rst
   config.rst
   persistence.rst
   config_logstash.rst
