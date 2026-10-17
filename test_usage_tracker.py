import argparse, contextlib, io, json, os, sqlite3, tempfile, unittest, subprocess, sys
from pathlib import Path
import usage_tracker as u
T='2026-09-25T10:00:00+00:00'
class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.db=u.connect(self.root/'data')
        self.project=self.root/'project'; self.project.mkdir()
    def tearDown(self): self.db.close(); self.temp.cleanup()
    def claude(self,id='msg1',output=4):
        return dict(timestamp=T,sessionId='s1',cwd=str(self.project),message=dict(id=id,model='opus',content='PRIVATE_SENTINEL',usage=dict(input_tokens=2,cache_read_input_tokens=10,cache_creation_input_tokens=3,output_tokens=output)))
    def test_streaming_and_fork_copies_deduplicated(self):
        u.consume(self.db,'claude',self.claude(),{}); u.consume(self.db,'claude',self.claude(output=8),{})
        copied=self.claude(output=8); copied['sessionId']='fork'; u.consume(self.db,'claude',copied,{})
        self.assertEqual(u.totals(self.db,[self.project])['claude/opus'],dict(input=2,cache_read=10,cache_write=3,output=8))
    def codex(self,total=100,cached=40,out=10):
        return dict(timestamp=T,payload=dict(type='token_count',info=dict(total_token_usage=dict(input_tokens=total,cached_input_tokens=cached,output_tokens=out)),rate_limits=dict(limit_id='codex',primary=dict(used_percent=3,window_minutes=10080,resets_at=1800000000))))
    def test_codex_cumulative_duplicates_and_cache_subset(self):
        c=dict(project=str(self.project),session='codex1',model='astra')
        for record in [self.codex(),self.codex(),self.codex(150,60,15)]: u.consume(self.db,'codex',record,c)
        self.assertEqual(u.totals(self.db,[self.project])['codex/astra'],dict(input=90,cache_read=60,cache_write=0,output=15))
        self.assertEqual(u.allowances(self.db)[0]['remaining_percent'],97)
    def test_codex_reset_and_fork_not_inherited(self):
        c=dict(project=str(self.project),session='fork',model='astra',forked=True)
        u.consume(self.db,'codex',self.codex(),c); u.consume(self.db,'codex',self.codex(110,40,12),c)
        u.consume(self.db,'codex',self.codex(5,0,1),c)
        self.assertEqual(u.totals(self.db,[self.project])['codex/astra']['input'],10)
        self.assertIn('reset',c['note'])
    def test_incremental_partial_line_truncation_and_privacy(self):
        logs=self.root/'logs'; logs.mkdir(); p=logs/'one.jsonl'
        p.write_text(json.dumps(self.claude())+'\n'+json.dumps(self.claude('msg2'))[:-1])
        first=u.sync(self.db,dict(claude=logs)); self.assertEqual(first['records_read'],1)
        with p.open('a') as f: f.write('}\n')
        self.assertEqual(u.sync(self.db,dict(claude=logs))['records_read'],1)
        self.assertEqual(u.sync(self.db,dict(claude=logs))['records_read'],0)
        p.write_text(json.dumps(self.claude())+'\n'); u.sync(self.db,dict(claude=logs))
        self.assertEqual(self.db.execute('select count(*) from events').fetchone()[0],2)
        self.db.commit(); self.assertNotIn(b'PRIVATE_SENTINEL',(self.root/'data/usage.sqlite3').read_bytes())
        self.assertEqual((self.root/'data/usage.sqlite3').stat().st_mode & 0o777,0o600)
    def test_snapshot_checkpoint_report_and_project_isolation(self):
        args=argparse.Namespace(project=str(self.project),include_project=[],milestone='M1',checkpoint='',event='start')
        u.snapshot(self.db,args,{})
        u.consume(self.db,'claude',self.claude(),{})
        other=self.claude('other'); other['cwd']=str(self.root/'other'); u.consume(self.db,'claude',other,{})
        args.checkpoint='A'; args.event='checkpoint'; u.snapshot(self.db,args,{})
        r=u.report(self.db,self.project,'M1'); self.assertEqual(r['tokens_between_snapshots']['claude/opus']['output'],4)
        self.assertEqual(len(r['intervals']),1)
    def test_reset_windows_never_subtracted(self):
        first=dict(allowances=[dict(provider='claude',bucket='seven_day',resets='a',used=90)])
        last=dict(allowances=[dict(provider='claude',bucket='seven_day',resets='b',used=2)])
        self.assertIsNone(u.allowance_changes(first,last)[0]['used_percentage_point_change'])
    def test_missing_and_expired_readings(self):
        self.assertEqual(u.allowances(self.db),[])
        u.limits(self.db,'claude',dict(seven_day=dict(used_percentage=75,resets_at=1)),T,'fixture')
        self.assertEqual(u.allowances(self.db)[0]['freshness'],'expired-window')
    def test_setup_preserves_existing_settings_and_display(self):
        settings=self.root/'settings.json'; settings.write_text(json.dumps(dict(extra={'keep':True},statusLine=dict(type='command',command='printf original',padding=2))))
        a=argparse.Namespace(settings=str(settings),data_dir=str(self.root/'setup'),apply=False)
        self.assertEqual(u.setup(a)['status'],'preview-only'); self.assertFalse((self.root/'setup').exists())
        a.apply=True; result=u.setup(a); saved=json.loads(settings.read_text())
        self.assertEqual(saved['extra'],{'keep':True}); self.assertEqual(saved['statusLine']['padding'],2)
        self.assertEqual(json.loads((self.root/'setup/statusline-delegate.json').read_text())['command'],'printf original')
        self.assertEqual(u.setup(a)['status'],'already-installed'); self.assertTrue(Path(result['backup']).exists())
        callback=subprocess.run([sys.executable,str(Path(u.__file__)), '--data-dir',a.data_dir,'statusline'],input=json.dumps(dict(rate_limits=dict(seven_day=dict(used_percentage=12,resets_at=1800000000)),prompt='PRIVATE_CALLBACK')),text=True,capture_output=True,check=True)
        self.assertEqual(callback.stdout,'original')
        captured=u.connect(a.data_dir); self.assertEqual(u.allowances(captured)[0]['remaining_percent'],88); captured.close()
        self.assertNotIn(b'PRIVATE_CALLBACK',(Path(a.data_dir)/'usage.sqlite3').read_bytes())
        saved['later']='preserve'; settings.write_text(json.dumps(saved))
        self.assertEqual(u.uninstall(a)['status'],'uninstalled')
        restored=json.loads(settings.read_text()); self.assertEqual(restored['later'],'preserve'); self.assertEqual(restored['statusLine']['command'],'printf original')
if __name__=='__main__': unittest.main()
