"""Tests for install-squawk.sh's download: retries, token and fallback.

A local HTTP server stands in for GitHub and serves the pinned squawk binary,
so the script's checksum still passes. The tests need that binary: set SQUAWK
to the path install-squawk.sh installed (the self-test workflow does); without
it they are skipped.

Run from scripts/migration-lint:  python3 -m unittest discover -s tests -v
"""

import http.server
import os
import subprocess
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(os.path.dirname(HERE), "install-squawk.sh")
SQUAWK = os.environ.get("SQUAWK")


class FakeRelease:
    """Answers each GET with the next status in `statuses` (200 once they run
    out); `refuse_token` answers 401 to any request that carries a token."""

    def __init__(self, body, statuses=(), refuse_token=False):
        self.body = body
        self.statuses = list(statuses)
        self.refuse_token = refuse_token
        self.requests = []  # Authorization header of each request, or None
        release = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                auth = self.headers.get("Authorization")
                release.requests.append(auth)
                if release.refuse_token and auth:
                    status = 401
                elif release.statuses:
                    status = release.statuses.pop(0)
                else:
                    status = 200
                payload = release.body if status == 200 else b"unavailable"
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/squawk" % self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


@unittest.skipUnless(SQUAWK, "set SQUAWK to the installed pinned squawk")
class InstallSquawkDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SQUAWK, "rb") as fh:
            cls.body = fh.read()

    def install(self, release, token=None):
        env = {k: v for k, v in os.environ.items() if k != "GH_DOWNLOAD_TOKEN"}
        env["SQUAWK_DOWNLOAD_URL"] = release.url
        if token:
            env["GH_DOWNLOAD_TOKEN"] = token
        with tempfile.TemporaryDirectory() as dest:
            result = subprocess.run(
                ["bash", INSTALL, dest], env=env, capture_output=True, text=True
            )
            installed = os.path.exists(os.path.join(dest, "squawk"))
        return result, installed

    def test_retries_a_504_then_installs(self):
        with FakeRelease(self.body, statuses=[504]) as release:
            result, installed = self.install(release)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(installed)
        self.assertEqual(len(release.requests), 2)
        self.assertIn("answered 504 (attempt 1 of 5)", result.stderr)

    def test_sends_the_token(self):
        with FakeRelease(self.body) as release:
            result, installed = self.install(release, token="ghs_test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(release.requests, ["Bearer ghs_test"])

    def test_falls_back_to_anonymous_when_the_token_is_refused(self):
        with FakeRelease(self.body, refuse_token=True) as release:
            result, installed = self.install(release, token="ghs_revoked")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(installed)
        self.assertEqual(release.requests, ["Bearer ghs_revoked", None])

    def test_does_not_retry_a_404(self):
        with FakeRelease(self.body, statuses=[404]) as release:
            result, installed = self.install(release)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(installed)
        self.assertEqual(len(release.requests), 1)
        self.assertIn("answered 404.", result.stderr)


if __name__ == "__main__":
    unittest.main()
