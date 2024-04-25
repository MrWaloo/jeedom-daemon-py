import sys
import os

sys.path.append(os.path.realpath(os.path.dirname(__file__) + '/..'))

# now we can import the module in the parent
# directory.

import unittest

from jeedomdaemon.base_config import BaseConfig

class TestBaseConfig(unittest.TestCase):
    def test_base_config_creation(self):
        """
        Test that it can create a basic config parser
        """
        config = BaseConfig()
        config.parse([])
        self.assertEqual(config.socket_host, "127.0.0.1")

    def test_base_config_parse(self):
        """
        Test that it can parse config
        """
        config = BaseConfig()
        config.parse(['--loglevel', 'info', '--socketport', '42000', '--callback', 'http://localhost/path', '--apikey', 'cnysltyql', '--pid', '123'])
        self.assertEqual(config.log_level, "info")
        self.assertEqual(config.socket_host, "127.0.0.1")
        self.assertEqual(config.socket_port, 42000)
        self.assertEqual(config.callback_url, "http://localhost/path")
        self.assertEqual(config.api_key, "cnysltyql")
        self.assertEqual(config.pid_filename, "123")

    def test_custom_config_parse(self):
        """
        Test that it can parse config
        """
        class TestConfig(BaseConfig):
            def __init__(self):
                super().__init__()
                self.add_argument("--clientId", help="my client Id", type=str)

            @property
            def clientId(self):
                return str(self._args.clientId)

        config = TestConfig()
        config.parse(['--clientId', 'hfldhfsd'])
        self.assertEqual(config.clientId, "hfldhfsd")



if __name__ == '__main__':
    unittest.main()