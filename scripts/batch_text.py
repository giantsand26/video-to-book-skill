#!/usr/bin/env python3
"""Prepare small JSON batches, accept checked results, resume and assemble.

prepare SOURCE WORKDIR [--mode translate|polish] [--all]
accept WORKDIR RESULT.json
finish WORKDIR OUTPUT.txt
No API dependency: each request file can be processed by any available model.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def save(path, data):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def records(path):
    raw = path.read_text()
    if path.suffix == '.json':
        rows = json.loads(raw)
        pairs = [(int(r['start']), r['text'].strip()) for r in rows if r['text'].strip()]
    else:
        matches = list(re.finditer(r'^\[(\d+):(\d{2})\]\s*', raw, re.M))
        pairs = [(int(m[1])*60+int(m[2]), raw[m.end():matches[i+1].start() if i+1<len(matches) else len(raw)].strip()) for i,m in enumerate(matches)]
    if not pairs or any(a[0]>b[0] for a,b in zip(pairs,pairs[1:])):
        raise ValueError('需要非空、按时间排列的转写JSON或带时间戳纯文本')
    return [{'id':i,'timestamp':f'{t//60:02d}:{t%60:02d}','text':text} for i,(t,text) in enumerate(pairs)]


def suspicious(text):
    return bool(re.search(r'[^，。！？；：,.!?;:\n]{65,}',text) or re.search(r'(.{8,30})\1{2,}',text))


def requests(work, state):
    pending = [r for r in state['source'] if str(r['id']) not in state['done']]
    batches, batch, size = [], [], 0
    for row in pending:
        if batch and (len(batch)>=12 or size+len(row['text'])>3000):
            batches.append(batch); batch=[]; size=0
        batch.append(row); size+=len(row['text'])
    if batch: batches.append(batch)
    paths=[]
    for batch in batches:
        # Content-addressed names prevent overwriting previously issued batches.
        key=hashlib.sha256(json.dumps(batch,ensure_ascii=False).encode()).hexdigest()[:16]
        path=work/f'request-{key}.json'
        save(path, {'instruction':state['instruction'], 'glossary':state['glossary'], 'records':batch})
        paths.append(path.name)
    save(work/'pending.json',paths)
    print(f"{len(state['done'])}/{len(state['source'])} accepted; {len(paths)} pending batches")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('source',type=Path); prep.add_argument('work',type=Path)
    prep.add_argument('--mode',choices=['translate','polish'],default='translate'); prep.add_argument('--all',action='store_true')
    prep.add_argument('--glossary',type=Path)
    accept=sub.add_parser('accept'); accept.add_argument('work',type=Path); accept.add_argument('result',type=Path)
    finish=sub.add_parser('finish'); finish.add_argument('work',type=Path); finish.add_argument('output',type=Path)
    args=p.parse_args(); work=args.work; statepath=work/'state.json'
    if args.command=='prepare':
        source=records(args.source)
        glossary=args.glossary.read_text() if args.glossary else ''
        signature=hashlib.sha256(json.dumps([source,args.mode,args.all,glossary],ensure_ascii=False).encode()).hexdigest()
        work.mkdir(parents=True,exist_ok=True)
        if statepath.exists():
            state=json.loads(statepath.read_text())
            if state['signature']!=signature: raise ValueError('输入或规则改变，请使用新的工作目录')
        else:
            instruction=('逐段忠实翻译成简体中文' if args.mode=='translate' else '按语义校订中文标点和明显ASR错字，捋顺语句')
            instruction+='。保留原意、口吻、问答和信息顺序。每个id、timestamp原样返回，text为处理后全文；不合并、不漏段、不总结。只返回JSON数组。'
            state={'signature':signature,'source':source,'instruction':instruction,'glossary':glossary,'done':{}}
            if args.mode=='polish' and not args.all:
                state['done']={str(r['id']):r for r in source if not suspicious(r['text'])}
        save(statepath,state); requests(work,state)
    elif args.command=='accept':
        state=json.loads(statepath.read_text()); result=json.loads(args.result.read_text())
        if not isinstance(result,list): raise ValueError('结果必须是JSON数组')
        ids=[r.get('id') for r in result if isinstance(r,dict)]
        rejected=[]
        for row in state['source']:
            key=str(row['id'])
            if key in state['done']: continue
            hits=[r for r in result if isinstance(r,dict) and r.get('id')==row['id']]
            if len(hits)==1 and hits[0].get('timestamp')==row['timestamp'] and isinstance(hits[0].get('text'),str) and hits[0]['text'].strip():
                state['done'][key]={**row,'text':hits[0]['text'].strip()}
            elif row['id'] in ids: rejected.append(row['id'])
        save(statepath,state); requests(work,state)
        if rejected: print('Rejected IDs:', rejected)
    else:
        state=json.loads(statepath.read_text())
        missing=[r['id'] for r in state['source'] if str(r['id']) not in state['done']]
        if missing: raise ValueError(f'尚缺 {len(missing)} 段，不能生成成稿：{missing[:20]}')
        text='\n\n'.join(f"[{r['timestamp']}] {state['done'][str(r['id'])]['text']}" for r in state['source'])+'\n'
        tmp=args.output.with_suffix(args.output.suffix+'.tmp'); tmp.write_text(text); tmp.replace(args.output)
        print(f'完整性检查通过：{len(state["source"])} 段。仍需抽查语义及时间戳对齐。')


if __name__=='__main__': main()
