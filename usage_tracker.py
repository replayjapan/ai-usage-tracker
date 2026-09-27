#!/usr/bin/env python3
"""AI Usage Tracker: local usage snapshots; no model calls or plugin dependency."""
import argparse, datetime as dt, hashlib, json, os, shlex, sqlite3, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
COLUMNS=('input','cache_read','cache_write','output')
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def stamp(v):
    try:
        if isinstance(v,(int,float)): return dt.datetime.fromtimestamp(v,dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(dt.timezone.utc).isoformat()
    except (ValueError,TypeError,AttributeError,OverflowError): return None
def num(v): return v if isinstance(v,(int,float)) and not isinstance(v,bool) and v>=0 else 0

def default_data_dir():
    if os.environ.get('AI_USAGE_TRACKER_DATA'): return Path(os.environ['AI_USAGE_TRACKER_DATA']).expanduser()
    if (ROOT/'data').is_dir(): return ROOT/'data'  # Existing standalone installations keep history.
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'ai-usage-tracker'

def connect(folder,read_only=False):
    if read_only:
        file=Path(folder).expanduser().resolve()/'usage.sqlite3'
        if not file.is_file(): return None
        db=sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=2)
        db.row_factory=sqlite3.Row; db.execute('PRAGMA query_only=ON'); return db
    p=Path(folder).expanduser().resolve(); p.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(p,0o700)
    db=sqlite3.connect(p/'usage.sqlite3',timeout=30); db.row_factory=sqlite3.Row; os.chmod(p/'usage.sqlite3',0o600)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,inode TEXT,offset INTEGER,context TEXT);
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,provider TEXT,session TEXT,project TEXT,model TEXT,observed TEXT,input INTEGER,cache_read INTEGER,cache_write INTEGER,output INTEGER);
    CREATE TABLE IF NOT EXISTS allowances(provider TEXT,bucket TEXT,observed TEXT,used REAL,resets TEXT,minutes REAL,source TEXT,PRIMARY KEY(provider,bucket,observed));
    CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,project TEXT,milestone TEXT,checkpoint TEXT,event TEXT,captured TEXT,payload TEXT);
    CREATE TABLE IF NOT EXISTS snapshot_keys(request_id TEXT PRIMARY KEY,payload TEXT);
    '''); return db

def event(db,key,provider,c,t,u):
    if not c.get('project') or not c.get('session') or not t: return
    db.execute('''INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
    input=max(input,excluded.input),cache_read=max(cache_read,excluded.cache_read),cache_write=max(cache_write,excluded.cache_write),output=max(output,excluded.output)''',
    (key,provider,c['session'],str(Path(c['project']).expanduser().resolve()),c.get('model') or 'unknown',t,*[int(num(u.get(k))) for k in COLUMNS]))

def limits(db,provider,data,t,source):
    if not isinstance(data,dict) or not t: return
    for name,w in data.items():
        if not isinstance(w,dict): continue
        used=w.get('used_percentage',w.get('used_percent'))
        if not isinstance(used,(int,float)) or isinstance(used,bool) or used<0: continue
        minutes=num(w.get('window_minutes',w.get('windowDurationMins'))) or {'seven_day':10080,'five_hour':300}.get(name)
        db.execute('INSERT OR REPLACE INTO allowances VALUES(?,?,?,?,?,?,?)',(provider,name,t,used,stamp(w.get('resets_at')),minutes,source))

def consume(db,provider,d,c):
    t=stamp(d.get('timestamp'))
    if provider=='claude':
        m=d.get('message') or {}; u=m.get('usage')
        if d.get('cwd'): c['project']=str(Path(d['cwd']).expanduser().resolve())
        c['session']=d.get('sessionId') or d.get('session_id') or c.get('session')
        c['model']=m.get('model') or c.get('model')
        if not isinstance(u,dict) or not m.get('id'): return
        # Same message can be emitted repeatedly while streaming or copied into a fork.
        event(db,'claude:'+m['id'],provider,c,t,dict(input=u.get('input_tokens'),cache_read=u.get('cache_read_input_tokens'),cache_write=u.get('cache_creation_input_tokens'),output=u.get('output_tokens')))
        return
    p=d.get('payload') or {}
    if d.get('type')=='session_meta':
        c['session']=p.get('id') or p.get('session_id')
        c['project']=str(Path(p['cwd']).resolve()) if p.get('cwd') else None
        c['forked']=bool(p.get('forked_from_id') or p.get('forked_from'))
    if d.get('type')=='turn_context': c['model']=p.get('model') or c.get('model')
    if p.get('type')!='token_count': return
    r=p.get('rate_limits')
    if isinstance(r,dict): limits(db,provider,{str(r.get('limit_id') or 'codex')+':'+k:v for k,v in r.items() if isinstance(v,dict)},t,'codex-log')
    u=(p.get('info') or {}).get('total_token_usage')
    if not isinstance(u,dict): return
    current={k:int(num(u.get(k))) for k in ('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens')}
    prev=c.get('total')
    if prev is None and c.get('forked'):
        c['total']=current; c['note']='Fork baseline omitted; first sample may include new usage.'; return
    prev=prev or dict.fromkeys(current,0)
    if any(current[k]<prev[k] for k in current):
        c['total']=current; c['note']='Counter reset baseline omitted.'; return
    diff={k:current[k]-prev[k] for k in current}; c['total']=current
    if not any(diff.values()): return
    # Codex cached input is a subset of input; reasoning is a subset of output.
    key='codex:'+str(c.get('session'))+':'+hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
    event(db,key,provider,c,t,dict(input=max(0,diff['input_tokens']-diff['cached_input_tokens']-diff['cache_write_input_tokens']),cache_read=diff['cached_input_tokens'],cache_write=diff['cache_write_input_tokens'],output=diff['output_tokens']))

def sync(db,roots):
    stats=dict(files_updated=0,records_read=0,malformed_records=0,unreadable_files=0,missing_roots=[],coverage_notes=[])
    for provider,root in roots.items():
        root=Path(root).expanduser()
        if not root.is_dir(): stats['missing_roots'].append(provider); continue
        for path in sorted(root.rglob('*.jsonl')):
            if path.is_symlink(): continue
            try:
                st=path.stat(); identity=f'{st.st_dev}:{st.st_ino}'
                old=db.execute('SELECT * FROM files WHERE path=?',(str(path),)).fetchone()
                same=old and old['inode']==identity and old['offset']<=st.st_size
                offset=old['offset'] if same else 0; c=json.loads(old['context']) if same else {}
                if offset==st.st_size: continue
                with path.open('rb') as f:
                    f.seek(offset)
                    while True:
                        begin=f.tell(); line=f.readline()
                        if not line or not line.endswith(b'\n'): offset=begin; break
                        offset=f.tell()
                        try:
                            d=json.loads(line)
                            if isinstance(d,dict): consume(db,provider,d,c)
                            stats['records_read']+=1
                        except (ValueError,TypeError,KeyError,AttributeError): stats['malformed_records']+=1
                db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',(str(path),identity,offset,json.dumps(c))); stats['files_updated']+=1
            except OSError: stats['unreadable_files']+=1
    stats['coverage_notes']=sorted({json.loads(r[0])['note'] for r in db.execute('SELECT context FROM files') if json.loads(r[0]).get('note')})
    db.commit(); return stats

def totals(db,projects):
    projects=[Path(p).expanduser().resolve() for p in projects]
    result={}
    for r in db.execute('SELECT provider,model,project,sum(input) i,sum(cache_read) r,sum(cache_write) w,sum(output) o FROM events GROUP BY provider,model,project'):
        path=Path(r['project'])
        if not any(path==p or p in path.parents for p in projects): continue
        v=result.setdefault(r['provider']+'/'+r['model'],dict.fromkeys(COLUMNS,0))
        for k,col in zip(COLUMNS,('i','r','w','o')): v[k]+=r[col]
    return result

def allowances(db):
    result=[]
    for r in db.execute('SELECT a.* FROM allowances a JOIN (SELECT provider,bucket,max(observed) t FROM allowances GROUP BY provider,bucket) b ON a.provider=b.provider AND a.bucket=b.bucket AND a.observed=b.t'):
        item=dict(r); age=max(0,(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(r['observed'])).total_seconds())
        expired=bool(r['resets'] and dt.datetime.fromisoformat(r['resets'])<=dt.datetime.now(dt.timezone.utc))
        item.update(remaining_percent=max(0,100-r['used']),age_seconds=round(age),freshness='expired-window' if expired else ('stale' if age>900 else 'recent'))
        result.append(item)
    return result

def snapshot(db,args,stats):
    request_id=getattr(args,'request_id',None)
    if request_id:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM snapshot_keys WHERE request_id=?',(request_id,)).fetchone()
        if row: db.commit(); return {**json.loads(row['payload']),'duplicate':True}
    projects=sorted({str(Path(p).expanduser().resolve()) for p in [args.project,*args.include_project]})
    payload=dict(captured_at=now(),projects=projects,totals=totals(db,[Path(p) for p in projects]),allowances=allowances(db),coverage=stats)
    payload['missing_allowance_providers']=sorted({'claude','codex'}-{r['provider'] for r in payload['allowances']})
    db.execute('INSERT INTO snapshots(project,milestone,checkpoint,event,captured,payload) VALUES(?,?,?,?,?,?)',(str(Path(args.project).resolve()),args.milestone,args.checkpoint,args.event,payload['captured_at'],json.dumps(payload)))
    if request_id: db.execute('INSERT INTO snapshot_keys VALUES(?,?)',(request_id,json.dumps(payload)))
    db.commit(); return payload

def difference(first,last):
    if first['projects']!=last['projects']: return None
    return {key:{k:last['totals'].get(key,{}).get(k,0)-first['totals'].get(key,{}).get(k,0) for k in COLUMNS} for key in first['totals'].keys()|last['totals'].keys()}

def allowance_changes(first,last):
    before={(r['provider'],r['bucket']):r for r in first['allowances']}; result=[]
    for r in last['allowances']:
        old=before.get((r['provider'],r['bucket'])); same=bool(old and old['resets'] and old['resets']==r['resets'])
        result.append(dict(provider=r['provider'],bucket=r['bucket'],scope='account-wide',
            used_percentage_point_change=r['used']-old['used'] if same else None,
            status='same-reset-window' if same else 'missing-baseline-or-reset-changed'))
    return result

def report(db,project,milestone):
    rows=db.execute('SELECT * FROM snapshots WHERE project=? AND milestone=? ORDER BY id',(str(Path(project).resolve()),milestone)).fetchall()
    if not rows: return dict(status='no-snapshots',milestone=milestone)
    payloads=[json.loads(r['payload']) for r in rows]; first,last=payloads[0],payloads[-1]
    return dict(milestone=milestone,status='needs-end-snapshot' if len(rows)<2 else ('recorded' if first['projects']==last['projects'] else 'project-scope-changed'),
        snapshots=[dict(event=r['event'],checkpoint=r['checkpoint'],at=r['captured']) for r in rows],
        tokens_between_snapshots=difference(first,last),allowance_changes=allowance_changes(first,last),
        intervals=[dict(from_event=rows[i-1]['event'],to_event=rows[i]['event'],checkpoint=rows[i]['checkpoint'],
                        tokens=difference(payloads[i-1],payloads[i])) for i in range(1,len(rows))],
        latest_allowances=last['allowances'],coverage=last['coverage'],notes=[
        'Only locally recorded usage between snapshots; not a complete account bill.',
        'Allowances are account-wide observations; reading logs does not query a fresh balance.',
        'Other sessions under the selected project roots are included. Use distinct milestone periods.',
        'A snapshot cannot include the current turn’s still-unreported final tokens.'])

def statusline(args):
    raw=sys.stdin.buffer.read(1024*1024)
    try:
        data=json.loads(raw); db=connect(args.data_dir); limits(db,'claude',data.get('rate_limits'),now(),'claude-statusline'); db.commit(); db.close()
    except Exception: pass
    config=Path(args.data_dir)/'statusline-delegate.json'
    try:
        command=json.loads(config.read_text()).get('command')
        if command:
            r=subprocess.run(command,shell=True,input=raw,stdout=subprocess.PIPE,timeout=8)
            sys.stdout.buffer.write(r.stdout); return
    except Exception: pass
    print('AI Usage Tracker')

def setup(args):
    settings=Path(args.settings).expanduser().resolve(); folder=Path(args.data_dir).expanduser().resolve()
    
    if settings.is_symlink(): raise ValueError('Settings is a symlink; no automatic modification.')
    old_text=settings.read_text() if settings.exists() else '{}\n'; d=json.loads(old_text); old=d.get('statusLine') or {}; cmd=old.get('command')
    command=shlex.join([sys.executable,str(folder/'statusline-launcher.py'),'--data-dir',str(folder),'statusline'])
    if cmd==command: return dict(status='already-installed')
    if old and (old.get('type')!='command' or not isinstance(cmd,str)): raise ValueError('Unsupported statusLine; settings unchanged.')
    if not args.apply: return dict(status='preview-only',settings_file=str(settings),command=command,preserves_existing_display=bool(cmd),next_step='After final placement, run setup-claude --apply.')
    if 'usage_tracker.py' in (cmd or ''): raise ValueError('Existing tracker wrapper detected; settings unchanged.')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(folder,0o700); delegate=folder/'statusline-delegate.json'
    if delegate.exists(): raise ValueError('Existing delegate configuration; settings unchanged.')
    refresh_launcher(folder)
    backup=folder/('claude-settings-before-'+dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.json')
    with backup.open('x') as f: os.chmod(backup,0o600); f.write(old_text)
    delegate.write_text(json.dumps(dict(command=cmd,statusLine=old or None))); os.chmod(delegate,0o600)
    d['statusLine']={**old,'type':'command','command':command}; settings.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=settings.parent,delete=False) as f:
        json.dump(d,f,indent=2); f.write('\n'); temporary=f.name
    os.replace(temporary,settings)
    return dict(status='installed',backup=str(backup),plugin_files_changed=False)

def uninstall(args):
    settings=Path(args.settings).expanduser().resolve(); folder=Path(args.data_dir).expanduser().resolve()
    d=json.loads(settings.read_text()); delegate=folder/'statusline-delegate.json'
    expected=shlex.join([sys.executable,str(Path(__file__).resolve()),'--data-dir',str(folder),'statusline'])
    stable=shlex.join([sys.executable,str(folder/'statusline-launcher.py'),'--data-dir',str(folder),'statusline'])
    if (d.get('statusLine') or {}).get('command') not in (expected,stable):
        return dict(status='not-our-wrapper',settings_changed=False)
    old=json.loads(delegate.read_text()).get('statusLine')
    if not args.apply: return dict(status='preview-only',instruction='uninstall-claude --apply restores only the previous statusLine setting.')
    if old is None: d.pop('statusLine',None)
    else: d['statusLine']=old
    with tempfile.NamedTemporaryFile(mode='w',dir=settings.parent,delete=False) as f:
        json.dump(d,f,indent=2); f.write('\n'); temporary=f.name
    os.replace(temporary,settings)
    delegate.rename(folder/('statusline-delegate-retired-'+dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.json'))
    return dict(status='uninstalled',usage_data_preserved=True)

def refresh_launcher(folder):
    """Private standalone copy: cache removal cannot break the configured callback."""
    folder=Path(folder).expanduser().resolve(); folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=folder,delete=False) as f:
        f.write(Path(__file__).read_text()); temporary=f.name
    os.replace(temporary,folder/'statusline-launcher.py')
    return dict(status='launcher-refreshed',settings_changed=False)

def main():
    os.umask(0o077); p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',default=str(default_data_dir()))
    p.add_argument('--claude-logs',default=str(Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path.home()/'.claude')))/'projects'))
    p.add_argument('--codex-logs',default=str(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'sessions'))
    subs=p.add_subparsers(dest='command',required=True)
    for cmd in ('sync','status','statusline','refresh-launcher'):
        parser=subs.add_parser(cmd)
        if cmd=='status': parser.add_argument('--read-only',action='store_true')
    s=subs.add_parser('setup-claude'); s.add_argument('--settings',default=str(Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path.home()/'.claude')))/'settings.json')); s.add_argument('--apply',action='store_true')
    s=subs.add_parser('uninstall-claude'); s.add_argument('--settings',default=str(Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path.home()/'.claude')))/'settings.json')); s.add_argument('--apply',action='store_true')
    s=subs.add_parser('snapshot'); s.add_argument('--project',default=os.getcwd()); s.add_argument('--include-project',action='append',default=[]); s.add_argument('--milestone',required=True); s.add_argument('--checkpoint',default=''); s.add_argument('--event',choices=['start','checkpoint','progress','end'],required=True); s.add_argument('--request-id')
    s=subs.add_parser('report'); s.add_argument('--project',default=os.getcwd()); s.add_argument('--milestone',required=True); s.add_argument('--read-only',action='store_true')
    a=p.parse_args()
    if a.command=='statusline': statusline(a); return
    if a.command=='setup-claude': print(json.dumps(setup(a),indent=2)); return
    if a.command=='uninstall-claude': print(json.dumps(uninstall(a),indent=2)); return
    if a.command=='refresh-launcher': print(json.dumps(refresh_launcher(a.data_dir),indent=2)); return
    readonly=getattr(a,'read_only',False)
    db=connect(a.data_dir,readonly)
    if db is None: print(json.dumps(dict(status='unavailable',read_only=True,reason='No existing usage database.'))); return
    if a.command=='report': result=report(db,a.project,a.milestone)
    elif readonly:
        result=dict(read_only=True,allowances=allowances(db),coverage='Previously imported records only; no logs scanned.')
    else:
        stats=sync(db,dict(claude=a.claude_logs,codex=a.codex_logs))
        result=snapshot(db,a,stats) if a.command=='snapshot' else dict(coverage=stats,allowances=allowances(db),missing_allowance_providers=sorted({'claude','codex'}-{r['provider'] for r in allowances(db)}))
    print(json.dumps(result,indent=2)); db.close()
if __name__=='__main__':
    try: main()
    except (OSError,ValueError,sqlite3.Error) as e: print('AI Usage Tracker: '+str(e),file=sys.stderr); sys.exit(1)
