"""services.single_instance：命名互斥体单实例锁。

每个用例都用**独立**的互斥体名，避免与真实运行中的程序、或与并行跑的其它测试
互相干扰。
"""
import unittest
import unittest.mock as mock
import uuid

from services import single_instance


class SingleInstanceTest(unittest.TestCase):
    def setUp(self):
        name = f"Global\\ThwTest_{uuid.uuid4().hex}"
        patcher = mock.patch.object(single_instance, "MUTEX_NAME", name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(single_instance.release)

    def test_first_acquire_succeeds(self):
        self.assertTrue(single_instance.acquire())

    def test_second_acquire_in_the_same_process_fails(self):
        # 同一进程内重复创建同名互斥体会拿到新句柄，但 GetLastError 报
        # ERROR_ALREADY_EXISTS —— 这正是判断"已经在运行"的依据。
        self.assertTrue(single_instance.acquire())
        self.assertFalse(single_instance.acquire())

    def test_release_then_acquire_succeeds_again(self):
        self.assertTrue(single_instance.acquire())
        single_instance.release()
        self.assertTrue(single_instance.acquire())

    def test_release_is_idempotent(self):
        single_instance.acquire()
        single_instance.release()
        single_instance.release()  # 不应抛出

    def test_release_without_acquire_is_safe(self):
        single_instance.release()  # 不应抛出


if __name__ == "__main__":
    unittest.main()
