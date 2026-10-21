"""Quit admission races and preservation of an actual running owned worker."""
import json
from pathlib import Path
import tempfile
import threading
import unittest

from server import Store


class QuitAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-QUIT-TEST-")
        self.store = Store(self.temporary.name)
        self.project = self.store.new_project({"name": "ENGINE TEST — quit preservation"})
        self.started = threading.Event()
        self.finish = threading.Event()
        self.worker_event = None

    def tearDown(self):
        self.finish.set()
        self.store.shutdown()
        self.temporary.cleanup()

    def start_worker(self):
        def work(job_id, progress, event):
            self.worker_event = event
            self.started.set()
            while not self.finish.wait(.01):
                if event.is_set():
                    raise RuntimeError("Owned test operation cancelled")
            return {"completed": True}
        job = self.store.submit(self.project["id"], "generate", work)
        self.assertTrue(self.started.wait(2))
        return job

    def test_declined_quit_preserves_running_job_and_workspace_admission(self):
        job = self.start_worker()
        response = self.store.prepare_quit({"cancel_active": False})
        self.assertFalse(response["ready"])
        self.assertEqual([job["id"]], [item["id"] for item in response["active_jobs"]])
        self.assertFalse(self.worker_event.is_set())
        self.assertEqual("running", self.store.job(job["id"])["state"])
        self.store.new_project({"name": "Still editable after declining quit"})
        self.finish.set()
        with self.store.lock:
            future = self.store.futures.get(job["id"])
        if future is not None: future.result(timeout=2)
        self.assertEqual("completed", self.store.job(job["id"])["state"])
        self.assertTrue(self.store.prepare_quit({"cancel_active": False})["ready"])
        with self.assertRaisesRegex(RuntimeError, "shutting down"):
            self.store.new_project({"name": "Cannot race a confirmed quit"})

    def test_explicit_cancellation_closes_admission_and_retains_reason(self):
        job = self.start_worker()
        result = self.store.prepare_quit({"cancel_active": True})
        self.assertTrue(result["ready"])
        self.assertTrue(self.worker_event.is_set())
        with self.assertRaisesRegex(RuntimeError, "shutting down"):
            self.store.submit(self.project["id"], "render", lambda *args: {})
        self.store.shutdown()
        self.assertEqual("cancelled", self.store.job(job["id"])["state"])
        receipt = json.loads((Path(self.temporary.name) / "last-session-exit.json").read_text())
        self.assertEqual("native-user-confirmed-job-cancellation", receipt["reason"])

    def test_non_boolean_or_ambiguous_quit_request_never_cancels(self):
        self.start_worker()
        for payload in ({}, {"cancel_active": "yes"}, {"cancel_active": 1}, {"cancel_active": True, "unknown": True}):
            with self.assertRaises(ValueError): self.store.prepare_quit(payload)
        self.assertFalse(self.worker_event.is_set())

    def test_queued_future_cancellation_is_terminal_and_releases_owned_input(self):
        entered, release, queued_done = threading.Event(), threading.Event(), threading.Event()
        cleaned = []

        def hold_first(job_id, progress, event):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("TEST worker release timed out")
            if event.is_set():
                raise RuntimeError("TEST running worker cancelled")
            return {"fixture": True}

        first = self.store.submit(self.project["id"], "generate", hold_first)
        self.assertTrue(entered.wait(2))
        queued = self.store.submit(self.project["id"], "render", lambda *args: self.fail("Cancelled queued work executed"),
                                   cleanup=lambda: cleaned.append("released"))
        future = self.store.futures[queued["id"]]
        future.add_done_callback(lambda _: queued_done.set())
        self.store.prepare_quit({"cancel_active": True})
        closer = threading.Thread(target=self.store.shutdown)
        try:
            closer.start()
            self.assertTrue(queued_done.wait(2), "Shutdown must settle queued work while the first worker is still exiting")
            self.assertTrue(future.cancelled())
            self.assertEqual(self.store.job(queued["id"])["state"], "cancelled")
        finally:
            release.set()
            closer.join(5)
        self.assertFalse(closer.is_alive())
        self.assertEqual(cleaned, ["released"])
        self.assertEqual(self.store.events, {})
        receipt = json.loads((Path(self.temporary.name) / "last-session-exit.json").read_text())
        self.assertEqual({record["id"]: record["state"] for record in receipt["terminal_jobs"]},
                         {first["id"]: "cancelled", queued["id"]: "cancelled"})
        persisted = json.loads((Path(self.temporary.name) / "jobs" / (queued["id"] + ".json")).read_text())
        self.assertEqual(persisted["state"], "cancelled")
        self.assertIsNotNone(persisted["finished_at"])

    def test_quit_cannot_split_durable_admission_from_executor_submission(self):
        original_lock = self.store.lock
        admitted, resume = threading.Event(), threading.Event()
        result, cleaned = {}, []

        class PauseAfterAdmission:
            """Yield at the first submitter lock boundary, without faking workers."""
            armed = True

            def __enter__(self):
                original_lock.acquire()
                return self

            def __exit__(self, *args):
                original_lock.release()
                if threading.current_thread() is submitter and self.armed:
                    self.armed = False
                    admitted.set()
                    if not resume.wait(5):
                        raise RuntimeError("TEST submission release timed out")

        self.store.lock = PauseAfterAdmission()

        def worker(job_id, progress, event):
            if event.wait(5):
                raise RuntimeError("TEST admitted worker cancelled")
            raise RuntimeError("TEST cancellation timed out")

        def submit():
            try:
                result["job"] = self.store.submit(self.project["id"], "render", worker,
                                                   cleanup=lambda: cleaned.append("released"))
            except Exception as exc:
                result["error"] = str(exc)

        submitter = threading.Thread(target=submit)
        try:
            submitter.start()
            self.assertTrue(admitted.wait(2))
            self.assertTrue(self.store.prepare_quit({"cancel_active": True})["ready"])
            self.store.shutdown()
        finally:
            resume.set()
            submitter.join(5)
            self.store.lock = original_lock
        self.assertFalse(submitter.is_alive())
        self.assertNotIn("error", result, "An accepted job must already own a Future before quit can close its executor")
        self.assertEqual(self.store.job(result["job"]["id"])["state"], "cancelled")
        self.assertEqual(cleaned, ["released"])
        self.assertEqual(self.store.events, {})


if __name__ == "__main__":
    unittest.main()
