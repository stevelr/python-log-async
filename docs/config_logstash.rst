.. _log-async-config:

Example Configuration
---------------------

Example ``log_async.conf`` for unencrypted TCP transport::

    input {
        tcp {
            host => "127.0.0.1"
            port => 5959
            mode => server
            codec => json
        }
    }


Example ``log_async.conf`` for SSL-encrypted TCP transport::

    input {
        tcp {
            host => "127.0.0.1"
            port => 5958
            mode => server
            codec => json

            ssl_enable => true
            ssl_verify => true
            ssl_extra_chain_certs => ["/etc/ssl/certs/log_async_ca.crt"]
            ssl_cert => "/etc/ssl/certs/log_async.crt"
            ssl_key => "/etc/ssl/private/log_async.key"
        }
    }
