"""Exercise HTTP boundaries without starting console polling or sending jobs."""
import http.client
import http.server
import json
import threading
import unittest
from web.server import Handler, TOKEN


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_local_status(self):
        status, body = self.request('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertIn('online', json.loads(body))

    def test_reject_foreign_host(self):
        status, _ = self.request('GET', '/api/status', headers={'Host': 'example.invalid'})
        self.assertEqual(status, 403)

    def test_reject_foreign_origin(self):
        status, _ = self.request('POST', '/api/task', '{}',
                                 {'Origin': 'https://example.invalid', 'X-Dashboard-Token': TOKEN})
        self.assertEqual(status, 403)

    def test_require_task_token(self):
        status, _ = self.request('POST', '/api/task', '{"task":"once"}')
        self.assertEqual(status, 403)

    def test_reject_unknown_task(self):
        status, body = self.request('POST', '/api/task', '{"task":"arbitrary"}',
                                    {'X-Dashboard-Token': TOKEN})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)['error'], 'Unknown task')


if __name__ == '__main__':
    unittest.main()
