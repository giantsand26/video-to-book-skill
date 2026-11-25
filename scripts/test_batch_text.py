import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('batch_text.py')


class ResumeTests(unittest.TestCase):
    def test_partial_resume_and_changed_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); src=root/'source.txt'; work=root/'batch'; out=root/'out.txt'
            src.write_text('[00:00] Hello.\n\n[136:02] Goodbye.\n')
            def run(*args):
                return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True)
            self.assertEqual(run('prepare',src,work).returncode,0)
            result=root/'result.json'
            result.write_text(json.dumps([{'id':0,'timestamp':'00:00','text':'你好。'},{'id':1,'timestamp':'00:02','text':'再见。'}]))
            self.assertEqual(run('accept',work,result).returncode,0)
            self.assertNotEqual(run('finish',work,out).returncode,0)
            self.assertFalse(out.exists())
            self.assertEqual(run('prepare',src,work).returncode,0)
            state=json.loads((work/'state.json').read_text())
            self.assertEqual(list(state['done']),['0'])
            pending=json.loads((work/'pending.json').read_text())
            self.assertEqual(json.loads((work/pending[0]).read_text())['records'][0]['id'],1)
            result.write_text(json.dumps([{'id':1,'timestamp':'136:02','text':'再见。'}]))
            self.assertEqual(run('accept',work,result).returncode,0)
            self.assertEqual(run('finish',work,out).returncode,0)
            self.assertEqual(out.read_text(),'[00:00] 你好。\n\n[136:02] 再见。\n')
            before=out.read_bytes()
            self.assertEqual(run('finish',work,out).returncode,0)
            self.assertEqual(out.read_bytes(),before)
            src.write_text('[00:00] Changed.\n')
            self.assertNotEqual(run('prepare',src,work).returncode,0)


if __name__=='__main__': unittest.main()
