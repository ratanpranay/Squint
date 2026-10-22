"""The updater trusts the update server the way translating does - public
roots and the computer's own - and tries the next way when one fails on
the certificate, not on anything else."""
import os
import ssl
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import translator, updater


class Trust(unittest.TestCase):
    def test_context_has_both_lists(self):
        translator._ssl_ctx = None
        ctx = translator.ssl_context()
        self.assertIsNotNone(ctx)
        self.assertGreater(ctx.cert_store_stats()["x509_ca"], 50)
        with open(translator.__file__, encoding="utf-8") as fh:
            self.assertIn("context.load_default_certs()", fh.read())

    def test_next_context_after_certificate_failure(self):
        calls = []

        def opener(request, timeout=None, context=None):
            calls.append(context)
            if len(calls) == 1:
                raise urllib.error.URLError(ssl.SSLCertVerificationError(
                    1, "unable to get local issuer certificate"))
            return "answer"
        with mock.patch.object(updater, "_contexts", lambda: ["a", "b"]), \
                mock.patch("urllib.request.urlopen", opener):
            self.assertEqual(updater._open("https://example.invalid"),
                             "answer")
        self.assertEqual(calls, ["a", "b"])

    def test_other_failures_are_not_retried(self):
        calls = []

        def opener(request, timeout=None, context=None):
            calls.append(context)
            raise urllib.error.URLError(OSError("no network"))
        with mock.patch.object(updater, "_contexts", lambda: ["a", "b"]), \
                mock.patch("urllib.request.urlopen", opener):
            with self.assertRaises(updater.UpdateError):
                updater._open("https://example.invalid")
        self.assertEqual(calls, ["a"])

    def test_missing_release_still_said_plainly(self):
        def opener(request, timeout=None, context=None):
            raise urllib.error.HTTPError("u", 404, "nf", {}, None)
        with mock.patch.object(updater, "_contexts", lambda: ["a"]), \
                mock.patch("urllib.request.urlopen", opener):
            with self.assertRaises(updater.UpdateError) as caught:
                updater._open("https://example.invalid")
        self.assertIn("No release", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
