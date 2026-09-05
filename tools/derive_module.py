"""Compose one immutable Module Layout guard release from committed original bytes."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, subprocess

ROOT=Path(__file__).resolve().parents[1]
BASELINE='e201075e052bfc71e7fef01f1360f319808cb78f'
GENERATION='202609051858'
PREFIX='solar-bess-topology-v7/module-layout/'
def blob(path):
    return subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':'+path])
def sha(raw): return hashlib.sha256(raw).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--generation',default=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M'));args=parser.parse_args()
    if not re.fullmatch(r'\d{12}',args.generation): raise SystemExit('Unique UTC timestamp required')
    release=ROOT/'releases'/args.generation
    if release.exists(): raise SystemExit('Immutable release already exists')
    baseline_raw=blob('releases/'+GENERATION+'/manifest.json');baseline=json.loads(baseline_raw)
    entry=PREFIX+'index.html';cartridge=PREFIX+'draw-readiness.js'
    insertion='<script src="./draw-readiness.js"></script>\n'
    files=[];prepared=[]
    for member in baseline['files']:
        if not member['path'].startswith(PREFIX):continue
        raw=blob('releases/'+GENERATION+'/'+member['path'])
        if sha(raw)!=member['sha256']:raise SystemExit('Baseline manifest mismatch')
        role='original'
        if member['path']==entry:
            if raw.count(b'</body>')!=1:raise SystemExit('Ambiguous entry insertion')
            raw=raw.replace(b'</body>',insertion.encode()+b'</body>');role='composed-entry'
        prepared.append((member['path'],raw,role))
    source='src/module-layout/draw-readiness.js';raw=(ROOT/source).read_bytes().replace(b'\r\n',b'\n')
    prepared.append((cartridge,raw,'cartridge'))
    release.mkdir(parents=True)
    for name,raw,role in prepared:
        target=release/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        files.append(dict(path=name,bytes=len(raw),sha256=sha(raw),role=role))
    siblings=[dict(path='solar-bess-topology-v7/dc-ac-lv-topology-review/index.html',repository='Ventusltd/layout-tool',commit=BASELINE,release=GENERATION,manifestSha256=sha(baseline_raw)),
      dict(path='solar-bess-topology-v7/cable-geometry-visualiser/index.html',repository='Ventusltd/cable-trench-or-drill',commit='76396fd3639dd86cddd21e392f29f43ab6d22f2d',release='202609051921',manifestSha256='a1b96236ba223bbbb8153538961bea677513a9fe3a877b9c61cd70d61128960e')]
    siblings+=baseline.get('crossOwnerNavigation',[])
    manifest=dict(schema='globalgrid.derived-runtime.v1',generation=args.generation,createdAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      baseline=dict(commit=BASELINE,generation=GENERATION,manifestSha256=sha(baseline_raw)),
      applications=[dict(id='module-layout',entry=entry)],files=files,
      composition=dict(entry=entry,insertBefore='</body>',insertion=insertion),cartridge=dict(path=cartridge,sourcePath=source),
      crossOwnerNavigation=siblings,rootOriginDependencies=baseline.get('rootOriginDependencies',[]),
      scope='Original formulas and runtime files preserved. Only entry composition and independent draw-readiness guard are new. No engineering acceptance claim.')
    raw=(json.dumps(manifest,indent=2)+'\n').encode();(release/'manifest.json').write_bytes(raw)
    pointer=dict(schema='globalgrid.derived-runtime-pointer.v1',generation=args.generation,manifest='releases/'+args.generation+'/manifest.json',manifestSha256=sha(raw))
    (ROOT/'derived-latest.json').write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps(pointer))
if __name__=='__main__':main()
