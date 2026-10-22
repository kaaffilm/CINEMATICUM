"""Installer ownership and pinned input gates; no test downloads a runtime."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import install_physical_rendering as installer


class PhysicalInstallerTests(unittest.TestCase):
    def test_both_platform_locks_have_complete_fixed_wheel_identities(self):
        for target in ("linux-x86_64-py312","macos-arm64-py313"):
            lock,digest=installer.load_lock(target)
            self.assertEqual(installer.PINNED_PACKAGES,{p["name"]:p["version"] for p in lock["packages"]})
            self.assertEqual(64,len(digest));self.assertGreater(sum(p["size"] for p in lock["packages"]),50000000)

    def test_dry_information_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            destination=Path(root)/"not-created/runtime";result=installer.info(destination)
            self.assertFalse(destination.parent.exists());self.assertFalse(result["destination_exists"])
            self.assertTrue(result["bounded_step"]);self.assertIn("llvm",result["external_prerequisites"])

    def test_existing_unmanaged_directory_is_never_modified(self):
        with tempfile.TemporaryDirectory() as root:
            destination=Path(root)/"runtime";destination.mkdir();existing=destination/"keep.txt";existing.write_bytes(b"user-installed")
            for check in (False,True):
                with self.subTest(check=check),self.assertRaisesRegex(ValueError,"unmanaged"):
                    installer.install(destination,check_only=check)
            self.assertEqual(b"user-installed",existing.read_bytes());self.assertEqual(["runtime"],[p.name for p in Path(root).iterdir()])

    def test_existing_unrelated_link_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);outside=root/"preserve";outside.mkdir();(outside/"keep").write_bytes(b"unchanged")
            destination=root/"runtime";destination.symlink_to(outside,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"unrelated"):installer.step(destination)
            self.assertEqual(b"unchanged",(outside/"keep").read_bytes());self.assertEqual(outside,destination.resolve())

    def test_cancellation_before_start_creates_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);event=threading.Event();event.set()
            with self.assertRaises(InterruptedError):installer.install(root/"new/runtime",cancel_event=event)
            self.assertEqual([],list(root.iterdir()))

    def test_corrupt_or_linked_cached_wheel_fails_without_admission(self):
        package=installer.load_lock()[0]["packages"][0]
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);cache=root/"cache";cache.mkdir();out=root/"out";out.mkdir()
            wheel=cache/package["filename"];wheel.write_bytes(b"different package bytes")
            with self.assertRaisesRegex(ValueError,"SHA-256"):installer._download_chunk(out,package,wheel_cache=cache)
            self.assertEqual([],list(out.iterdir()));self.assertEqual(b"different package bytes",wheel.read_bytes())
            wheel.unlink();preserve=root/"preserve";preserve.write_bytes(b"owned elsewhere");wheel.symlink_to(preserve)
            with self.assertRaisesRegex(ValueError,"symbolic"):installer._download_chunk(out,package,wheel_cache=cache)
            self.assertEqual(b"owned elsewhere",preserve.read_bytes());self.assertEqual([],list(out.iterdir()))

    def test_inventory_records_real_bytes_empty_metadata_and_links(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);(root/"empty").write_bytes(b"");(root/"binary").write_bytes(b"real payload")
            (root/"alias").symlink_to("binary");(root/installer.RECEIPT).write_text("not self-hashed")
            values=installer._inventory(root)
            self.assertEqual({"link":"binary"},values["alias"])
            self.assertEqual(0,values["empty"]["bytes"])
            self.assertEqual(hashlib.sha256(b"real payload").hexdigest(),values["binary"]["sha256"])
            self.assertNotIn(installer.RECEIPT,values)

    def test_changed_verifier_before_publication_retains_owned_resumable_state(self):
        # This is the journal/commit gate only; real CPU engine acceptance is
        # separately exercised by the physical runtime tests and installer.
        with tempfile.TemporaryDirectory() as root:
            destination=Path(root)/"runtime"
            installer.step(destination)
            journal=destination.parent/installer.PENDING
            state,_=installer._read(journal)
            runtime=installer._runtime_from_state(destination,state,installer.load_lock()[1])
            old={"versions":installer.PINNED_PACKAGES,"worker_sha256":"a"*64}
            current={**old,"worker_sha256":"b"*64}
            installer._save_state(runtime/"physical-acceptance.json",old)
            state["phase"]="publish";installer._save_state(journal,state)
            owner=(runtime/"owner.json").read_bytes()
            with patch.object(installer,"probe_runtime",return_value=current):
                with self.assertRaisesRegex(ValueError,"resume setup"):
                    installer.step(destination)
                self.assertFalse(destination.exists());self.assertFalse((runtime/installer.RECEIPT).exists())
                self.assertEqual("verify",installer._read(journal)[0]["phase"])
                self.assertEqual(owner,(runtime/"owner.json").read_bytes())
                self.assertEqual("publish",installer.step(destination)["phase"])
                self.assertEqual(current,installer._read(runtime/"physical-acceptance.json")[0])


if __name__=="__main__":unittest.main()
