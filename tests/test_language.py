"""Compiler/runtime tests isolated from live engines and credential stores."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread
import time
import unittest

from nacre import builtin
from nacre.contracts import Capability, NacreError, validate, fingerprint
from nacre.language import compile_source
from nacre.runtime import Runtime


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nacre-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.caps=builtin.get_capabilities()

    def plan(self,source,caps=None): return compile_source(source,caps or self.caps,workspace=self.root)
    def run_source(self,source,**kwargs): return Runtime(self.caps,builtin.invoke,self.root,workers=kwargs.pop("workers",4)).run(self.plan(source),**kwargs)
    def good(self,source,expected):
        result=self.run_source(source)
        self.assertEqual(result["status"],"passed",result)
        self.assertEqual(result["emitted"],expected)
        return result
    def bad_compile(self,source,code=None):
        with self.assertRaises(NacreError) as caught: self.plan(source)
        if code: self.assertEqual(caught.exception.code,code)
    def bad_run(self,source,code):
        result=self.run_source(source)
        self.assertEqual(result["status"],"failed",result)
        self.assertEqual(result["error"]["code"],code)

    def test_arithmetic_precedence(self): self.good("let a: Number = 2 + 3 * 4; verify a == 14; emit a;",[14])
    def test_exponent_associativity(self): self.good("let a: Number = 2 ^ 3 ^ 2; emit a;",[512])
    def test_unary_exponent_precedence(self): self.good("let a: Number = -2 ^ 2; emit a;",[-4])
    def test_scientific_notation(self): self.good("let a: Number = 1.25e2 / 5; emit a;",[25.0])
    def test_unicode_string_escaping(self): self.good('let a: String = "naïve\\nλ"; emit a;',["naïve\nλ"])
    def test_string_list_addition(self): self.good('let a: String = "a" + "b"; let b: List = [1] + [2]; emit a; emit b;',["ab",[1,2]])
    def test_forward_dependencies(self): self.good("let a: Integer = b + 1; let b: Integer = 41; emit a;",[42])
    def test_record_and_index(self): self.good('let r: Record = {name:"nacre",items:[4,8]}; let a: Integer = r.items[1]; emit a;',[8])
    def test_bool_is_not_integer(self): self.good("verify true != 1; emit true;",[True])
    def test_short_circuit(self): self.good("verify true or (1/0 == 0); verify not (false and (1/0 == 0)); emit 42;",[42])
    def test_null_identity(self): self.good("let a: Null = null; verify a == null; emit a;",[None])
    def test_alias_capability(self): self.good('use c = "core"; task a: Number <- c.sum(values=[1,2,3]); emit a;',[6])
    def test_empty_program(self): self.good("# empty\n",[])
    def test_syntax_requires_semicolon(self): self.bad_compile("let a: Number = 1","SYNTAX")
    def test_invalid_character(self): self.bad_compile("let a: Number = @;","SYNTAX")
    def test_invalid_string_escape(self): self.bad_compile('let a: String = "\\q";',"SYNTAX")
    def test_arbitrary_host_code_rejected(self): self.bad_compile('import os; os.system("echo unsafe");',"SYNTAX")
    def test_host_expression_call_rejected(self): self.bad_compile('let a: Any = __import__("os");',"SYNTAX")
    def test_duplicate_binding(self): self.bad_compile("let a: Integer = 1; let a: Integer = 2;","DUPLICATE")
    def test_duplicate_argument(self): self.bad_compile("task a: Number <- core.sum(values=[1],values=[2]);","DUPLICATE")
    def test_unknown_binding(self): self.bad_compile("let a: Integer = absent + 1;","NAME")
    def test_cycle(self): self.bad_compile("let a: Integer = b; let b: Integer = a;","CYCLE")
    def test_unknown_namespace(self): self.bad_compile('use a = "not_installed";',"CAPABILITY")
    def test_unknown_capability(self): self.bad_compile("task a: Number <- core.absent();","CAPABILITY")
    def test_unknown_type(self): self.bad_compile("let a: Unicorn = 1;","TYPE")
    def test_assignment_type_error(self): self.bad_compile('let a: Number = "one";',"TYPE")
    def test_bool_arithmetic_type_error(self): self.bad_compile("let a: Number = true + 1;","TYPE")
    def test_capability_input_type_error(self): self.bad_compile('task a: Number <- core.sum(values="one");',"TYPE")
    def test_missing_argument(self): self.bad_compile("task a: Number <- core.sum();","ARGUMENT")
    def test_unknown_argument(self): self.bad_compile("task a: Number <- core.sum(values=[],extra=1);","ARGUMENT")
    def test_unsafe_retry(self): self.bad_compile('task a: Artifact <- io.write_json(value=1,filename="a.json") retry 1;',"RETRY")
    def test_verify_requires_bool(self): self.bad_compile("verify 1;","TYPE")
    def test_division_zero(self): self.bad_run("let a: Number = 1/0;","ARITHMETIC")
    def test_missing_dynamic_field(self): self.bad_run("let a: Record = {x:1}; let b: Number = a.missing;","INDEX")
    def test_dynamic_type_violation(self): self.bad_run('let a: Record = {x:"text"}; let b: Number = a.x;',"TYPE")
    def test_failed_verification(self): self.bad_run("verify 1 == 2;","VERIFY")
    def test_nonfinite_result(self): self.bad_compile("let a: Number = 1e309;","VALUE")
    def test_power_resource_bound(self): self.bad_run("let a: Number = 2 ^ 10001;","LIMIT")

    def test_include_module(self):
        (self.root/"lib.nac").write_text("let base: Integer = 40;",encoding="utf-8")
        self.good('include "lib.nac"; let result: Integer = base+2; emit result;',[42])
    def test_include_duplicate_is_once(self):
        (self.root/"lib.nac").write_text("let a: Integer = 42;",encoding="utf-8")
        self.good('include "lib.nac"; include "lib.nac"; emit a;',[42])
    def test_include_cycle(self):
        (self.root/"a.nac").write_text('include "b.nac";',encoding="utf-8")
        (self.root/"b.nac").write_text('include "a.nac";',encoding="utf-8")
        self.bad_compile('include "a.nac";',"MODULE")
    def test_include_escape(self): self.bad_compile('include "../outside.nac";',"MODULE")
    def test_include_missing(self): self.bad_compile('include "missing.nac";',"MODULE")

    def test_data_pipeline(self):
        source='task t: Table <- data.table(rows=[{id:1,price:10},{id:2,price:20}],source="test"); task d: Table <- data.derive(table=t,source_column="price",column="gross",operator="*",value=2); task f: Table <- data.filter(table=d,column="gross",operator=">",value=30); task p: Table <- data.project(table=f,columns=["id","gross"]); emit p.rows;'
        self.good(source,[[{"id":2,"gross":40}]])
    def test_explicit_conversion(self):
        self.good('task t: Table <- data.table(rows=[{n:"1.25"}],source="test"); task c: Table <- data.convert(table=t,column="n",target="Number"); emit c.rows[0].n;',[1.25])
    def test_conversion_error(self):
        self.bad_run('task t: Table <- data.table(rows=[{n:"bad"}],source="test"); task c: Table <- data.convert(table=t,column="n",target="Number");',"CONVERSION")
    def test_join_type_mismatch(self):
        self.bad_run('task l: Table <- data.table(rows=[{id:1}],source="l"); task r: Table <- data.table(rows=[{id:"1"}],source="r"); task j: Table <- data.join(left=l,right=r,left_key="id",right_key="id");',"CONVERSION")
    def test_join_output_provenance(self):
        result=self.good('task l: Table <- data.table(rows=[{id:1}],source="l"); task r: Table <- data.table(rows=[{id:1,value:42}],source="r"); task j: Table <- data.join(left=l,right=r,left_key="id",right_key="id"); emit j.rows; emit j.provenance;',[[{"left_id":1,"right_id":1,"right_value":42}],{"left":"l","right":"r","keys":["id","id"]}])
    def test_table_contract_rejects_bad_row(self):
        with self.assertRaises(NacreError): validate({"$type":"Table","source":"x","schema":[{"name":"id","type":"Integer"}],"rows":[{"id":"wrong"}]},"Table")
    def test_table_is_not_record(self):
        table=builtin.invoke("data.table",{"rows":[{"id":1}],"source":"x"},{})
        with self.assertRaises(NacreError): validate(table,"Record")
    def test_object_identity_requires_origin(self):
        self.good('task l: Object <- core.object(origin="a",kind="product",id="1",revision="v1",ownership="borrowed"); task r: Object <- core.object(origin="b",kind="product",id="1",revision="v1",ownership="borrowed"); task same: Bool <- core.same_object(left=l,right=r); verify not same; emit same;',[False])
    def test_object_identity_revision_is_separate(self):
        self.good('task l: Object <- core.object(origin="a",kind="product",id="1",revision="v1",ownership="borrowed"); task r: Object <- core.object(origin="a",kind="product",id="1",revision="v2",ownership="borrowed"); task same: Bool <- core.same_object(left=l,right=r); verify same; emit same;',[True])
    def test_write_no_overwrite_and_artifact_hash(self):
        program='task a: Artifact <- io.write_json(value={x:42},filename="test.json"); task ok: Bool <- core.artifact_verify(artifact=a); verify ok; emit ok;'
        self.good(program,[True]); self.bad_run(program,"EXISTS")
    def test_output_escape_rejected(self): self.bad_run('task a: Artifact <- io.write_json(value=1,filename="../escape.json");',"PATH")
    def test_controlled_retry(self):
        result=self.good('task a: Number <- demo.flaky(value=42,key="retry") retry 1; emit a;',[42])
        self.assertEqual(sum(e["event"]=="retry" for e in result["events"]),1)

    def test_resume_after_failure(self):
        program='let base: Number = 40; task a: Number <- demo.flaky(value=base+2,key="resume"); verify a == 42; emit a;'
        checkpoint=self.root/"checkpoint.json"
        first=self.run_source(program,checkpoint=checkpoint)
        self.assertEqual(first["status"],"failed")
        second=self.run_source(program,checkpoint=checkpoint,resume=True)
        self.assertEqual(second["status"],"passed",second)
        self.assertIn("cache_hit",[e["event"] for e in second["events"]])
        self.assertEqual(second["emitted"],[42])
    def test_checkpoint_tamper(self):
        path=self.root/"checkpoint.json"; program="let a: Integer = 42; emit a;"
        self.run_source(program,checkpoint=path)
        data=json.loads(path.read_text()); data["status"]="tampered"; path.write_text(json.dumps(data))
        with self.assertRaises(NacreError): self.run_source(program,checkpoint=path,resume=True)
    def test_checkpoint_changed_program(self):
        path=self.root/"checkpoint.json"; self.run_source("let a: Integer = 1;",checkpoint=path)
        with self.assertRaises(NacreError): self.run_source("let a: Integer = 2;",checkpoint=path,resume=True)
    def test_resume_reads_again_and_invalidate_dependents(self):
        caps={"fake.read":Capability("fake.read",{},"Integer",effect="read",retry_safe=True)}
        state={"value":1,"calls":0}
        def invoke(n,a,c): state["calls"]+=1; return state["value"]
        plan=self.plan("task a: Integer <- fake.read(); let b: Integer = a+1; emit b;",caps)
        path=self.root/"checkpoint.json"
        first=Runtime(caps,invoke,self.root).run(plan,checkpoint=path)
        state["value"]=2
        second=Runtime(caps,invoke,self.root).run(plan,checkpoint=path,resume=True)
        self.assertEqual(first["emitted"],[2]); self.assertEqual(second["emitted"],[3]); self.assertEqual(state["calls"],2)
    def test_bad_external_output_rejected(self):
        caps={"fake.bad":Capability("fake.bad",{},"Number")}
        result=Runtime(caps,lambda n,a,c:"wrong",self.root).run(self.plan("task a: Number <- fake.bad();",caps))
        self.assertEqual(result["status"],"failed"); self.assertEqual(result["error"]["code"],"TYPE")
    def test_failure_stops_dependent(self):
        caps={"fake.bad":Capability("fake.bad",{},"Integer"),"fake.next":Capability("fake.next",{"value":"Integer"},"Integer")}
        calls=[]
        def invoke(n,a,c):
            calls.append(n)
            if n=="fake.bad": raise NacreError("EXPECTED","controlled failure")
            return 42
        result=Runtime(caps,invoke,self.root).run(self.plan("task a: Integer <- fake.bad(); task b: Integer <- fake.next(value=a);",caps))
        self.assertEqual(result["status"],"failed"); self.assertEqual(calls,["fake.bad"]); self.assertIn("b",result["pending"])
    def test_determinism_across_worker_counts(self):
        source="let a: Integer = b+1; let b: Integer = 41; let c: Integer = a*2; verify c == 84; emit c; emit a;"
        runs=[self.run_source(source,workers=n) for n in (1,2,4,1)]
        self.assertTrue(all(r["status"]=="passed" for r in runs))
        self.assertTrue(all(r["emitted"]==[84,42] for r in runs))
    def test_actual_concurrency(self):
        caps={"fake.work":Capability("fake.work",{"value":"Integer"},"Integer")}
        guard=Lock(); state={"active":0,"peak":0}
        def invoke(n,a,c):
            with guard: state["active"]+=1; state["peak"]=max(state["peak"],state["active"])
            time.sleep(.035)
            with guard: state["active"]-=1
            return a["value"]
        result=Runtime(caps,invoke,self.root,workers=4).run(self.plan("task a: Integer <- fake.work(value=1); task b: Integer <- fake.work(value=2); let c: Integer = a+b; emit c;",caps))
        self.assertEqual(result["emitted"],[3]); self.assertEqual(state["peak"],2); self.assertEqual(state["active"],0)
    def test_resource_serialization(self):
        caps={"fake.work":Capability("fake.work",{},"Integer",effect="read",resource="same")}
        guard=Lock(); state={"active":0,"peak":0}
        def invoke(n,a,c):
            with guard: state["active"]+=1; state["peak"]=max(state["peak"],state["active"])
            time.sleep(.025)
            with guard: state["active"]-=1
            return 1
        result=Runtime(caps,invoke,self.root).run(self.plan("task a: Integer <- fake.work(); task b: Integer <- fake.work();",caps))
        self.assertEqual(result["status"],"passed"); self.assertEqual(state["peak"],1); self.assertEqual(state["active"],0)
    def test_cancellation(self):
        event=Event(); event.set()
        result=self.run_source("let a: Integer = 1;",cancel_event=event)
        self.assertEqual(result["status"],"cancelled"); self.assertNotIn("a",result["results"])
    def test_active_cancellation_cleanup(self):
        event=Event()
        thread=Thread(target=lambda:(time.sleep(.02),event.set()))
        thread.start()
        result=self.run_source("task a: Number <- core.wait(value=1,milliseconds=1000); let b: Number = a+1;",cancel_event=event)
        thread.join()
        self.assertEqual(result["status"],"cancelled"); self.assertNotIn("b",result["results"])
    def test_worker_limit(self):
        with self.assertRaises(NacreError): Runtime(self.caps,builtin.invoke,self.root,workers=0)
    def test_cli_in_new_process(self):
        source=self.root/"cli.nac"; source.write_text("let a: Number = 6*7; verify a == 42; emit a;")
        result=subprocess.run([sys.executable,"-m","nacre.cli","run",str(source),"--workspace",str(self.root)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)["emitted"],[42])
    def test_cli_invalid_exit(self):
        source=self.root/"cli.nac"; source.write_text('let a: Number = "invalid";')
        result=subprocess.run([sys.executable,"-m","nacre.cli","check",str(source)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,2); self.assertEqual(json.loads(result.stdout)["error"]["code"],"TYPE")


if __name__=="__main__": unittest.main()
