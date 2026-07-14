import os
import time
import unittest

from tiktok_stats import reap_child_processes


class ReapChildProcessesTest(unittest.TestCase):
    @unittest.skipIf(os.name != "posix", "waitpid reaping is POSIX-only")
    def test_reaps_exited_child_process(self) -> None:
        pid = os.fork()
        if pid == 0:
            os._exit(0)

        deadline = time.time() + 2
        reaped = 0
        while time.time() < deadline:
            reaped += reap_child_processes()
            if reaped:
                break
            time.sleep(0.05)

        self.assertGreaterEqual(reaped, 1)


if __name__ == "__main__":
    unittest.main()
