import logging
import socket
import sys
import os
from logging.handlers import SysLogHandler

class ContextFilter(logging.Filter):
    hostname = socket.gethostname()
    def filter(self, record):
        record.hostname = ContextFilter.hostname
        return True

class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())
            sys.stderr.write(line + '\n')

    def flush(self):
        pass  # This could be implemented if buffering is used

    def isatty(self):
        return False

formatter = logging.Formatter('%(message)s')

if 'PAPERTRAIL' in os.environ:
    host, port = os.environ['PAPERTRAIL'].split(":")
    port = int(port)
    try:
        syslog = SysLogHandler(address=(host, port))
        syslog.addFilter(ContextFilter())
        env = os.environ.get('ENV', 'env?')
        format = f'%(message)s'
        formatter = logging.Formatter(format)
        syslog.setFormatter(formatter)
        syslogger = logging.getLogger('_sc_')

        #stdout_handler = logging.StreamHandler(sys.stdout)
        #stdout_handler.setLevel(logging.DEBUG)

        syslogger.addHandler(syslog)
        #syslogger.addHandler(stdout_handler)       
        #syslogger.setLevel(logging.DEBUG)
        print("CONNECT LOGGING TO PAPERTRAIL: ", ('logs6.papertrailapp.com', 33600))

        # Step 3: Replace sys.stdout with logging redirector
        sys.stdout = StreamToLogger(syslogger, logging.DEBUG)

    except:
        syslogger = logging.getLogger('_sc_')
else:
    syslogger = logging.getLogger('_sc_')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    syslogger.addHandler(handler)

if os.environ.get('DEBUG'):
    syslogger.setLevel(logging.DEBUG)
class MyLogger:
    def __init__(self, logger) -> None:
        self._logger = logger
        
    def debug(self, *args, **kwargs):
        try:
            self._logger.debug(" ".join(map(str, args)))
        except Exception as e:
            print("Logger error: ", e)

    def info(self, *args, **kwargs):
        self._logger.info(" ".join(map(str, args)))

    def warn(self, *args, **kwargs):
        self._logger.warn(" ".join(map(str, args)))

    def error(self, *args, **kwargs):
        self._logger.error(" ".join(map(str, args)))

logger = MyLogger(syslogger)




