"""Fixed runtime admission and complete, read-only pinned download discovery."""
import copy
import importlib
import threading
import unittest

import runtime_management as runtime


class RuntimeManagementTests(unittest.TestCase):
    def test_only_fixed_runtime_identities_can_choose_installers(self):
        payload={"operation":"install","lock_sha256":"0"*64}
        for value in ("../../server","os","physical;run",{},None):
            with self.subTest(value=value),self.assertRaises(ValueError):runtime.validate_request(value,payload)

    def test_client_paths_commands_urls_and_unknown_operations_are_rejected(self):
        basic={"operation":"check","lock_sha256":"0"*64}
        for payload in ({**basic,"python":"/usr/bin/python"},{**basic,"destination":"/tmp/runtime"},
                        {**basic,"url":"https://example.com/package"},{**basic,"command":"code"},
                        {**basic,"operation":"delete"},{**basic,"operation":[]},{"operation":"install"}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):runtime.validate_request("physical",payload)

    def test_actual_physical_lock_identity_is_required_and_normalization_is_pure(self):
        entry=runtime.describe("physical");self.assertTrue(entry["can_install"],entry["reason"])
        payload={"operation":"install","lock_sha256":entry["lock_sha256"]};before=copy.deepcopy(payload)
        self.assertEqual(payload,runtime.validate_request("physical",payload));self.assertEqual(before,payload)
        with self.assertRaisesRegex(ValueError,"changed"):runtime.validate_request("physical",{**payload,"lock_sha256":"0"*64})

    def test_discovery_distinguishes_presence_from_engine_verification(self):
        result=runtime.inventory();self.assertEqual(set(runtime.RUNTIMES),{row["id"] for row in result["runtimes"]})
        physical=next(row for row in result["runtimes"] if row["id"]=="physical")
        self.assertEqual(sum(d["bytes"] for d in physical["downloads"]),physical["download_bytes"])
        self.assertTrue(physical["download_bytes_complete"]);self.assertIn("llvm",physical["prerequisites"])
        self.assertIn(physical["managed_state"],{"present_unverified","not_installed","pending"})
        self.assertNotEqual("verified",physical["managed_state"])

    def test_download_totals_do_not_count_archived_source_members_twice(self):
        package={"name":"a","url":"https://primary/a","sha256":"a"*64,"size":11}
        archive={"name":"source","url":"https://primary/source","sha256":"b"*64,"bytes":23,
                 "files":[{"path":"file.py","size":10000,"sha256":"c"*64}]}
        downloads,complete=runtime._downloads({"packages":[package],"sources":[archive],"models":{"same":package}})
        self.assertTrue(complete);self.assertEqual(34,sum(d["bytes"] for d in downloads));self.assertEqual(2,len(downloads))
        archive.pop("bytes");downloads,complete=runtime._downloads({"sources":[archive]})
        self.assertFalse(complete);self.assertIsNone(downloads[0]["bytes"])

    def test_cancellation_prevents_install_without_mutating_the_runtime(self):
        event=threading.Event();event.set();entry=runtime.describe("physical")
        with self.assertRaises(InterruptedError):runtime.run("physical",{"operation":"check","lock_sha256":entry["lock_sha256"]},cancel_event=event)
        self.assertFalse(runtime._JOB_LOCK.locked())

    def test_setup_admission_refuses_a_second_live_job(self):
        entry=runtime.describe("physical");runtime._JOB_LOCK.acquire()
        try:
            with self.assertRaisesRegex(ValueError,"Another managed"):
                runtime.run("physical",{"operation":"check","lock_sha256":entry["lock_sha256"]})
        finally:runtime._JOB_LOCK.release()


if __name__=="__main__":unittest.main()
