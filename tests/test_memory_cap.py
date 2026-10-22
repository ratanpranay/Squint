"""The offline engine is started with a cap on the memory it keeps."""
import unittest
from unittest import mock

from app import offline_model as om


class MemoryCap(unittest.TestCase):
    def launched(self, gb, gpu):
        seen = {}

        class Proc:
            def poll(self):
                return None

        def popen(command, **kw):
            seen["cmd"] = command
            return Proc()

        class Reply:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch.object(om, "_memory_gb", return_value=gb), \
                mock.patch.object(om, "model_path", return_value="m.gguf"), \
                mock.patch.object(om, "engine_flavor", return_value="standard"), \
                mock.patch.object(om.subprocess, "Popen", popen), \
                mock.patch.object(om.urllib.request, "urlopen",
                                  return_value=Reply()):
            om._launch("/x/llama-server", "hymt", gpu)
        cmd = seen["cmd"]
        return cmd, int(cmd[cmd.index("--cache-ram") + 1])

    def test_capped_on_every_machine(self):
        for gb in (8, 16, 32):
            for gpu in (True, False):
                cmd, mb = self.launched(gb, gpu)
                ctx = int(cmd[cmd.index("-c") + 1])
                self.assertLessEqual(mb, 1536)
                # model 1.1 GB + working memory (~64 KB a token) + kept
                # + ~0.3 GB for the sums stays under 4 GB.
                total = 1.1 + ctx * 64 / 1024 / 1024 + mb / 1024 + 0.3
                self.assertLess(total, 4.0, (gb, gpu, total))

    def test_less_kept_on_small_memory(self):
        self.assertEqual(self.launched(8, True)[1], 1024)
        self.assertEqual(self.launched(16, True)[1], 1536)


if __name__ == "__main__":
    unittest.main()
