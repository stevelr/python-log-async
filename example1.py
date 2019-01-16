# -*- coding: utf-8 -*-

import logging
import sys

from log_async.handler import AsynchronousLogHandler

host = 'localhost'
port = 5959

test_logger = logging.getLogger('python-log-async-logger')
test_logger = logging.getLogger('')
test_logger.setLevel(logging.INFO)
test_logger.addHandler(AsynchronousLogHandler(host, port, database_path='log_async_test.db'))

test_logger.error('python-log-async: test log-async error message.')
test_logger.info('python-log-async: test log-async info message.')
test_logger.warning('python-log-async: test log-async warning message.')
test_logger.debug('python-log-async: test log-async debug message.')

try:
    1 / 0
except Exception as e:
    test_logger.exception(u'Exception: %s', e)

# add extra field to log-async message
extra = {
    'test_string': 'python version: ' + repr(sys.version_info),
    'test_boolean': True,
    'test_dict': {'a': 1, 'b': 'c'},
    'test_float': 1.23,
    'test_integer': 123,
    'test_list': [1, 2, '3'],
}
test_logger.info('python-log-async: test extra fields', extra=extra)
