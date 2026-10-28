"""Durable evidence and checkpoint destination preservation."""
import json
from pathlib import Path
import tempfile
import unittest
from nacre import api,builtin
from nacre.contracts import NacreError
from nacre.language import compile_source
from nacre.runtime import Runtime

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nacre-api-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_checkpoint_preserves_existing_unrelated_json(self):
        path=self.root/"precious.json"; original=b'{"source":"keep"}'
        path.write_bytes(original)
        caps=builtin.get_capabilities()
        plan=compile_source("let x: Integer = 42;",caps,workspace=self.root)
        with self.assertRaises(NacreError) as caught: Runtime(caps,builtin.invoke,self.root).run(plan,checkpoint=path)
        self.assertEqual(caught.exception.code,"CHECKPOINT")
        self.assertEqual(path.read_bytes(),original)

    def test_receipt_digest_and_artifact_bytes(self):
        result=api.execute('task a: Artifact <- io.write_json(value={answer:42},filename="answer.json"); verify true; emit a;',workspace=self.root)
        saved=api.save_receipt(result,self.root)
        self.assertTrue(api.verify_receipt(saved["receipt"],self.root)["verified"])
        Path(result["emitted"][0]["path"]).write_text("changed")
        self.assertFalse(api.verify_receipt(saved["receipt"],self.root)["verified"])

    def test_receipt_result_tamper_detected(self):
        result=api.execute("let answer: Integer = 42; emit answer;",workspace=self.root)
        saved=api.save_receipt(result,self.root)
        path=Path(saved["receipt"]); content=json.loads(path.read_text()); content["result"]["emitted"]=[43]
        path.write_text(json.dumps(content))
        self.assertFalse(api.verify_receipt(path,self.root)["verified"])

    def test_receipt_path_escape_rejected(self):
        with self.assertRaises(NacreError): api.verify_receipt(self.root/"outside.json",self.root)

    def test_failed_execution_receipt_is_not_verified(self):
        result=api.execute("verify false;",workspace=self.root)
        saved=api.save_receipt(result,self.root)
        self.assertFalse(api.verify_receipt(saved["receipt"],self.root)["verified"])
