"""Preservation, immutable transport and selected-source extraction gates."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request

import install_learned_tracking as installer


class LearnedInstallerTests(unittest.TestCase):
    def test_observed_official_cdn_redirect_preserves_ranges_and_rejects_other_hosts(self):
        handler=installer._TrustedRedirects()
        request=Request("https://huggingface.co/facebook/model/resolve/frozen/checkpoint.pt",
                        headers={"Range":"bytes=4194304-8388607","Accept-Encoding":"identity"})
        target="https://us.aws.cdn.hf.co/owned-object?signature=example"
        redirected=handler.redirect_request(request,None,302,"Found",{},target)
        self.assertEqual(target,redirected.full_url)
        self.assertEqual("bytes=4194304-8388607",redirected.get_header("Range"))
        self.assertEqual("identity",redirected.get_header("Accept-encoding"))
        for denied in ("https://us.aws.cdn.hf.co.example.org/object","https://example.org/object",
                       "http://us.aws.cdn.hf.co/object","https://name:secret@us.aws.cdn.hf.co/object"):
            with self.subTest(denied=denied),self.assertRaisesRegex(ValueError,"outside the official"):
                handler.redirect_request(request,None,302,"Found",{},denied)

    def test_platform_closure_includes_real_sources_weights_and_cpu_packages(self):
        for target,total in (("linux-x86_64-py312",562427090),("macos-arm64-py313",444586928)):
            lock,digest=installer.load_lock(target)
            self.assertEqual(len(digest),64)
            self.assertEqual(sum(item["size"] for item in lock["downloads"]),total)
            self.assertEqual(len(lock["packages"]),28)
            self.assertEqual({"sam2","tapir"},set(lock["models"]))
            self.assertEqual({"sam2","tapnet"},{s["package"] for s in lock["sources"]})
            torch=next(item for item in lock["packages"] if item["name"]=="torch")
            self.assertEqual("2.8.0+cpu" if target.startswith("linux") else "2.8.0",torch["version"])
            self.assertFalse(any("cuda" in item["name"] or item["name"].startswith("nvidia-") for item in lock["packages"]))

    def test_read_only_information_and_cancelled_start_create_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);destination=root/"new/runtime"
            report=installer.info(destination)
            self.assertTrue(report["bounded_step"]);self.assertFalse(destination.parent.exists())
            event=threading.Event();event.set()
            with self.assertRaises(InterruptedError):installer.install(destination,cancel_event=event)
            self.assertEqual([],list(root.iterdir()))

    def test_existing_user_directory_and_unrelated_link_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);original=root/"original";original.mkdir();(original/"keep").write_bytes(b"user runtime")
            for check in (False,True):
                with self.assertRaisesRegex(ValueError,"unmanaged"):
                    installer.install(original,check_only=check)
            alias=root/"candidate";alias.symlink_to(original,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"unrelated"):installer.step(alias)
            self.assertEqual(b"user runtime",(original/"keep").read_bytes())
            self.assertEqual(original,alias.resolve())
            self.assertEqual({"original","candidate"},{p.name for p in root.iterdir()})

    def test_cached_artifact_tampering_and_symbolic_links_are_rejected(self):
        package=installer.load_lock()[0]["packages"][0]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);cache=root/"cache";cache.mkdir();output=root/"out";output.mkdir()
            cached=cache/package["filename"];cached.write_bytes(b"substituted wheel")
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                installer._download_chunk(output,package,download_cache=cache)
            self.assertEqual([],list(output.iterdir()));cached.unlink()
            original=root/"unrelated";original.write_bytes(b"keep")
            cached.symlink_to(original)
            with self.assertRaisesRegex(ValueError,"symbolic"):
                installer._download_chunk(output,package,download_cache=cache)
            self.assertEqual(b"keep",original.read_bytes());self.assertEqual([],list(output.iterdir()))

    def test_selected_source_extraction_preserves_bytes_and_rejects_member_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runtime=root/"runtime";runtime.mkdir();archive=root/"source.tar.gz"
            code=b"# literal official-style source; never imported by extraction\nvalue = 7\n"
            records=[{"path":"sam2/model.py","size":len(code),"sha256":hashlib.sha256(code).hexdigest()}]
            with tarfile.open(archive,"w:gz") as tar:
                member=tarfile.TarInfo("upstream-commit/sam2/model.py");member.size=len(code);tar.addfile(member,io.BytesIO(code))
                member=tarfile.TarInfo("upstream-commit/ignored/setup.py");data=b"raise RuntimeError('must never execute')";member.size=len(data);tar.addfile(member,io.BytesIO(data))
            source={"filename":archive.name,"package":"sam2","files":records,"size":archive.stat().st_size,
                    "sha256":hashlib.sha256(archive.read_bytes()).hexdigest()}
            installer.extract_source(archive,source,runtime,"3.12")
            installed=runtime/"lib/python3.12/site-packages/sam2/model.py"
            self.assertEqual(installed.read_bytes(),code)
            self.assertFalse((runtime/"lib/python3.12/site-packages/ignored").exists())
            installer.extract_source(archive,source,runtime,"3.12")
            installed.write_bytes(b"local change")
            with self.assertRaisesRegex(ValueError,"different bytes"):
                installer.extract_source(archive,source,runtime,"3.12")
            self.assertEqual(b"local change",installed.read_bytes())
            linked=root/"linked.tar.gz"
            with tarfile.open(linked,"w:gz") as tar:
                member=tarfile.TarInfo("upstream-commit/sam2/model.py");member.type=tarfile.SYMTYPE;member.linkname="../../outside";tar.addfile(member)
            bad={**source,"filename":linked.name,"size":linked.stat().st_size,"sha256":hashlib.sha256(linked.read_bytes()).hexdigest()}
            with self.assertRaisesRegex(ValueError,"linked"):
                installer.extract_source(linked,bad,runtime,"3.12")
            self.assertFalse((root/"outside").exists())

    def test_full_inventory_detects_added_changed_removed_files_without_following_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/"empty").write_bytes(b"");(root/"weight").write_bytes(b"actual bytes")
            (root/"alias").symlink_to("weight");(root/installer.RECEIPT).write_bytes(b"excluded self")
            first=installer._inventory(root)
            self.assertEqual(first["alias"],{"link":"weight"});self.assertEqual(first["empty"]["bytes"],0)
            self.assertNotIn(installer.RECEIPT,first)
            (root/"weight").write_bytes(b"different bytes")
            self.assertNotEqual(first,installer._inventory(root))
            (root/"weight").write_bytes(b"actual bytes");(root/"new.py").write_bytes(b"new source")
            self.assertNotEqual(first,installer._inventory(root))
            (root/"new.py").unlink();(root/"empty").unlink()
            self.assertNotEqual(first,installer._inventory(root))

    def test_changed_acceptance_source_returns_to_integrity_and_real_probe_phases(self):
        lock,digest=installer.load_lock()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);destination=root/installer.VERSION
            name=installer.VERSION+"-"+"a"*32
            runtime=root/installer.VERSIONS_DIRECTORY/name;runtime.mkdir(parents=True)
            state={"schema":"cinematicum-learned-pending","version":1,"destination":str(destination),
                   "lock_sha256":digest,"runtime_name":name,"base_python":"/owned/base/python",
                   "phase":"publish","index":0}
            owner={key:state[key] for key in ("schema","version","destination","lock_sha256","runtime_name","base_python")}
            installer._save(runtime/"owner.json",owner,True)
            installer._save(root/installer.PENDING,state,True)
            before={"versions":{"torch":"2.8.0+cpu"},"worker_sha256":"1"*64}
            current={**before,"worker_sha256":"2"*64}
            installer._save(runtime/"learned-verification.json",before,True)
            (runtime/"acceptance-sam2.json").write_bytes(b"preserved old probe")
            with patch.object(installer,"probe_runtime",return_value=current):
                with self.assertRaisesRegex(ValueError,"changed before publication"):
                    installer.step(destination)
                self.assertFalse(destination.exists())
                self.assertEqual("verify",json.loads((root/installer.PENDING).read_text())["phase"])
                self.assertEqual(b"preserved old probe",(runtime/"acceptance-sam2.json").read_bytes())
                result=installer.step(destination)
            self.assertEqual("probe-sam2",result["phase"])
            self.assertEqual(current,json.loads((runtime/"learned-verification.json").read_text()))
            self.assertFalse(destination.exists())


if __name__=="__main__":unittest.main()
