"""Installed/frozen distribution boundaries, independent of optional engines."""
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from nacre import adapters, api, builtin
from nacre.contracts import NacreError
from nacre.identity import module_fingerprint
from nacre.runtime import _implementation_digest


@contextmanager
def working_directory(path):
    previous=Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PublicPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nacre-public-")
        self.addCleanup(self.temp.cleanup)
        # Windows CI TEMP may use an 8.3 alias or junction; compare canonical paths.
        self.root=Path(self.temp.name).resolve()/"workspace space ü"
        self.root.mkdir()
        self.env=patch.dict(os.environ,{"NACRE_GENESIS9_ROOT":"","NACRE_GENESIS10_ROOT":""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def cli(self,*args):
        return subprocess.run([sys.executable,"-m","nacre",*args],cwd=self.root,capture_output=True,timeout=30)

    def source(self,text,name="program.nac"):
        path=self.root/name
        path.write_text(text,encoding="utf-8")
        return path

    def test_api_defaults_workspace_to_current_directory(self):
        with working_directory(self.root):
            result=api.execute('task artifact: Artifact <- io.write_json(value={text:"héllo 世界"},filename="héllo.json"); emit artifact;')
            saved=api.save_receipt(result)
            self.assertTrue(api.verify_receipt(saved["receipt"])["verified"])
        self.assertEqual(result["status"],"passed")
        self.assertTrue(Path(result["emitted"][0]["path"]).is_relative_to(self.root/"outputs"))

    def test_cli_default_workspace_receipt_and_unicode_json(self):
        source=self.source('task file: Artifact <- io.write_json(value={message:"Hello, 世界 🐚"},filename="héllo.json"); emit file;')
        process=self.cli("run",str(source),"--receipt")
        self.assertEqual(process.returncode,0,process.stderr)
        result=json.loads(process.stdout.decode("utf-8"))
        artifact=Path(result["emitted"][0]["path"])
        self.assertTrue(artifact.is_relative_to(self.root/"outputs"))
        self.assertEqual(json.loads(artifact.read_text(encoding="utf-8")),{"message":"Hello, 世界 🐚"})
        verified=self.cli("verify",result["receipt"])
        self.assertEqual(verified.returncode,0,verified.stderr)
        self.assertTrue(json.loads(verified.stdout)["verified"])
        artifact.write_text("changed",encoding="utf-8")
        self.assertEqual(self.cli("verify",result["receipt"]).returncode,1)

    def test_cli_includes_resolve_inside_user_workspace(self):
        self.source("let included: Integer = 42;","module.nac")
        main=self.source('include "module.nac"; verify included == 42; emit included;')
        process=self.cli("run",str(main))
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout)["emitted"],[42])

    def test_sqlite_queries_require_no_genesis_installation(self):
        with patch.object(adapters,"_load9",side_effect=AssertionError("optional integration imported")):
            adapters.invoke("db.demo",{"source":"sqlite","value":42},{"workspace":self.root})
            result=adapters.invoke("db.query",{"source":"sqlite","sql":"SELECT value FROM nacre11_demo_values WHERE id=:id","params":{"id":1}},{"workspace":self.root})
        self.assertEqual(result["rows"],[{"value":42}])
        self.assertTrue(result["read_only"])

    def test_sqlite_select_rejects_mutation_and_multiple_statements(self):
        context={"workspace":self.root}
        adapters.invoke("db.demo",{"source":"sqlite","value":42},context)
        for sql in ("DELETE FROM nacre11_demo_values","PRAGMA writable_schema=ON","SELECT 1; DELETE FROM nacre11_demo_values","SELECT 1 -- comment"):
            with self.subTest(sql=sql),self.assertRaises(NacreError) as caught:
                adapters.invoke("db.query",{"source":"sqlite","sql":sql},context)
            self.assertEqual(caught.exception.code,"ARGUMENT")
        result=adapters.invoke("db.query",{"source":"sqlite","sql":"SELECT :value AS expected;","params":{"value":42}},context)
        self.assertEqual(result["rows"],[{"expected":42}])

    def test_optional_capabilities_are_visible_but_unavailable(self):
        discovered=api.discover()
        self.assertEqual(len(discovered["capabilities"]),30)
        self.assertTrue(discovered["availability"]["db.query"]["available"])
        self.assertFalse(discovered["availability"]["math.diff"]["available"])
        self.assertFalse(discovered["availability"]["repo.roundtrip"]["available"])
        result=api.execute('task value: Symbolic <- math.diff(expression="x^2");',workspace=self.root)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["error"]["code"],"UNAVAILABLE")
        self.assertIn("NACRE_GENESIS9_ROOT",result["error"]["message"])

    def test_explicit_invalid_optional_root_is_not_silently_replaced(self):
        with patch.dict(os.environ,{"NACRE_GENESIS9_ROOT":str(self.root/"missing")}):
            self.assertFalse(adapters.capability_availability()["math.diff"]["available"])
            with self.assertRaises(NacreError) as caught:
                adapters._load9()
        self.assertEqual(caught.exception.code,"UNAVAILABLE")

    def test_portable_fingerprints_do_not_contain_developer_paths(self):
        keys=adapters.dependency_fingerprints()
        self.assertEqual(set(keys),{"nacre.adapters","sqlite_version"})
        self.assertEqual(len(keys["nacre.adapters"]),64)

    def test_identity_does_not_read_module_file_path(self):
        import nacre.builtin
        initial=module_fingerprint("nacre.builtin")
        with patch.object(nacre.builtin,"__file__",str(self.root/"absent.py")):
            self.assertEqual(module_fingerprint("nacre.builtin"),initial)
            self.assertEqual(builtin.get_capabilities()["core.sum"].implementation,initial)

    def test_frozen_identity_ignores_ephemeral_extraction_prefix(self):
        with patch.object(sys,"frozen",True,create=True):
            with patch.object(sys,"base_prefix",str(self.root/"_MEI-first")):
                first=_implementation_digest()
            with patch.object(sys,"base_prefix",str(self.root/"_MEI-second")):
                second=_implementation_digest()
        self.assertEqual(first,second)

    def test_malformed_receipt_is_structured(self):
        root=self.root/"outputs/runs"
        root.mkdir(parents=True)
        receipt=root/"bad.json"
        for content in ("not json","[]",'{"result":{},"result_sha256":null}'):
            receipt.write_text(content,encoding="utf-8")
            with self.subTest(content=content),self.assertRaises(NacreError) as caught:
                api.verify_receipt(receipt,self.root)
            self.assertEqual(caught.exception.code,"RECEIPT")

    def test_nonfinite_and_deep_receipts_are_structured_without_traceback(self):
        root=self.root/"outputs/runs"
        root.mkdir(parents=True)
        receipt=root/"nonportable.json"
        values=("NaN","Infinity","-Infinity","1e999","["*1500+"0"+"]"*1500)
        for value in values:
            receipt.write_text('{"result":{"status":"passed","emitted":['+value+']},"result_sha256":"'+'a'*64+'"}',encoding="utf-8")
            with self.subTest(value=value[:40]):
                with self.assertRaises(NacreError) as caught:
                    api.verify_receipt(receipt,self.root)
                self.assertEqual(caught.exception.code,"RECEIPT")
                process=self.cli("verify",str(receipt))
                self.assertEqual(process.returncode,2,process.stderr)
                self.assertEqual(json.loads(process.stdout)["error"]["code"],"RECEIPT")
                self.assertNotIn(b"Traceback",process.stderr)

    def test_cli_help_and_error_exit_codes(self):
        self.assertEqual(self.cli("--help").returncode,0)
        self.assertIn(b"Nacre-11 0.1.0",self.cli("--version").stdout)
        for text,expected in (("let answer: Integer = ;",2),("let answer: Integer = 1 / 0;",2),("emit 1 / 0;",1)):
            process=self.cli("run",str(self.source(text)))
            self.assertEqual(process.returncode,expected,process.stdout)
        self.assertEqual(self.cli("run",str(self.root/"missing.nac")).returncode,2)


if __name__=="__main__":
    unittest.main()
