import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("identity",Path(__file__).parents[1]/"scripts/site_identity_bridge.py")
identity=importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)

class IdentityTests(unittest.TestCase):
    def test_mapping_keeps_namespaces_and_ambiguity_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"fixture.db"
            with sqlite3.connect(path) as c:
                c.execute("CREATE TABLE annotation_cases(case_id TEXT PRIMARY KEY)")
                c.execute("CREATE TABLE legacy_term_case_links(legacy_case_id INTEGER,v2_case_id TEXT)")
                c.executemany("INSERT INTO annotation_cases VALUES (?)",[("v2:a",),("v2:b",)])
                c.executemany("INSERT INTO legacy_term_case_links VALUES (?,?)",[(1,"v2:a"),(1,"v2:b"),(2,"missing")])
            c.close()
            before=path.read_bytes()
            self.assertEqual(identity.audit_targets(path,"main",["1","2"]),{"1":["v2:a","v2:b"],"2":[]})
            self.assertEqual(identity.audit_targets(path,"annotation",["1"]),{"1":[]})
            self.assertEqual(identity.audit_targets(path,"v2",["v2:a","missing"]),{"v2:a":["v2:a"],"missing":[]})
            self.assertEqual(before,path.read_bytes())

if __name__=="__main__":unittest.main()
