import argparse, json, os, re, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import usage_tracker as u

def privacy_issue(name, text):
    if re.search(r'(^|/)(data|\.env[^/]*)(/|$)|\.sqlite3|settings-before|statusline-delegate|statusline-launcher', name): return 'private artifact'
    if re.search(r'/(?:Users|home)/[A-Za-z0-9_.-]+/', text): return 'personal home path'
    if re.search(r'(?i)-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|(?:sk-ant-|ghp_)[A-Za-z0-9_-]{20,}', text): return 'credential material'
    return None

class PackagingTests(unittest.TestCase):
    def test_human_guide_and_plugin_metadata(self):
        text=(u.ROOT/'README.md').read_text()
        self.assertLess(text.index('## FOR HUMANS'),text.index('## FOR AI BROTHREN'))
        self.assertIn('/plugin install ai-usage-tracker@ai-usage-tracker',text)
        self.assertNotIn('repository name and visibility are not yet selected',text)
        plugin=json.loads((u.ROOT/'.claude-plugin/plugin.json').read_text())
        marketplace=json.loads((u.ROOT/'.claude-plugin/marketplace.json').read_text())
        self.assertEqual(plugin['version'],'0.1.2')
        self.assertEqual(plugin['license'],'MIT')
        self.assertTrue(plugin['author']['name']); self.assertTrue(marketplace['metadata']['description'])
        self.assertIn('MIT License',(u.ROOT/'LICENSE').read_text())

    def test_snapshot_retry_key_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            db=u.connect(folder)
            args=argparse.Namespace(project=folder,include_project=[],milestone='m',checkpoint='',event='start',request_id='same-request')
            u.snapshot(db,args,{})
            self.assertTrue(u.snapshot(db,args,{})['duplicate'])
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0],1); db.close()
    def test_read_only_does_not_create_or_change_database(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'private'; self.assertIsNone(u.connect(p,True)); self.assertFalse(p.exists())
            db=u.connect(p); db.close(); before=(p/'usage.sqlite3').read_bytes()
            ro=u.connect(p,True)
            with self.assertRaises(sqlite3.OperationalError): ro.execute("DELETE FROM snapshots")
            ro.close()
            for args in [['status','--read-only'],['report','--read-only','--milestone','fixture']]:
                r=subprocess.run([sys.executable,str(u.ROOT/'usage_tracker.py'),'--data-dir',str(p),*args],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr); json.loads(r.stdout)
            self.assertEqual((p/'usage.sqlite3').read_bytes(),before)
            self.assertEqual(sorted(x.name for x in p.iterdir()),['usage.sqlite3'])

    def test_environment_data_override_and_stable_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'AI_USAGE_TRACKER_DATA':folder}): self.assertEqual(u.default_data_dir(),Path(folder))
            u.refresh_launcher(folder); launcher=Path(folder)/'statusline-launcher.py'
            r=subprocess.run([sys.executable,str(launcher),'--data-dir',folder,'status','--read-only'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(json.loads(r.stdout)['status'],'unavailable')
            self.assertFalse((Path(folder)/'usage.sqlite3').exists())

    def test_public_tree_privacy(self):
        root=u.ROOT
        if (root/'.git').exists():
            names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root).decode().split('\0')
        else:
            # Legacy standalone data is private, never part of the proposed package.
            names=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and not any(x in {'data','__pycache__','.git'} for x in p.relative_to(root).parts)]
        for name in filter(None,names):
            p=root/name
            self.assertIsNone(privacy_issue(name,p.read_text(errors='replace')),f'Privacy issue in {name}')
        self.assertEqual(privacy_issue('data/usage.sqlite3',''),'private artifact')

    def test_manifests(self):
        manifest=json.loads((u.ROOT/'.claude-plugin/plugin.json').read_text())
        marketplace=json.loads((u.ROOT/'.claude-plugin/marketplace.json').read_text())
        self.assertEqual(manifest['version'],'0.1.2')
        self.assertEqual(marketplace['plugins'][0]['name'],manifest['name'])

if __name__=='__main__': unittest.main()
