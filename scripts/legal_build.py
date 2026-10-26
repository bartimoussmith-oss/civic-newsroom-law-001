import argparse
from datetime import datetime,timezone
import gzip
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urljoin,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
import engine

REPO='bartimoussmith-oss/civic-newsroom-law-001'
HOSTS={'wyoleg.gov','www.wyoleg.gov','www.wyocourts.gov','wyocourts.gov','www.govinfo.gov','govinfo.gov','www.supremecourt.gov','www.cheyennecity.org','www.laramiecountywy.gov'}
CAP=512*1024*1024
RX=[('wy_statute',re.compile(r'\b(?:W\.?\s*S\.?|Wyo(?:ming)?\.?\s+Stat(?:utes?)?\.?)\s*(?:§+\s*)?(?P<id>\d{1,2}-\d{1,2}-\d{1,4}(?:\.\d+)?)',re.I)),('us_code',re.compile(r'\b(?P<title>\d{1,2})\s+U\.?S\.?C\.?\s*(?:§+\s*)?(?P<id>\d+[A-Za-z]*(?:-\d+)?)',re.I)),('cfr',re.compile(r'\b(?P<title>\d{1,2})\s+C\.?F\.?R\.?\s*(?:§+\s*)?(?P<id>\d+(?:\.\d+)*)',re.I)),('wy_case',re.compile(r'\b(?P<id>\d{4}\s+WY\s+\d+)\b',re.I)),('us_case',re.compile(r'\b(?P<id>\d+\s+U\.?S\.?\s+\d+)\b',re.I)),('city_code',re.compile(r'\bCheyenne(?:\s+Municipal)?\s+Code\s*(?:§+\s*)?(?P<id>\d+\.\d+(?:\.\d+)?)',re.I))]

def dump(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def size(root):return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())
def check_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):raise ValueError('Source outside approved HTTPS hosts')
    return url
class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return super().redirect_request(req,fp,code,msg,headers,check_url(newurl))
def fetch(url):
    time.sleep(.4)
    with build_opener(Redirects()).open(Request(check_url(url),headers={'User-Agent':'CivicNewsroomLegalArchive/1.0'}),timeout=45) as r:
        final=check_url(r.geturl());raw=r.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ValueError('Source exceeds initial 32 MiB acquisition budget')
        return raw,final
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.href=None;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href');self.text=[]
    def handle_data(self,data):
        if self.href:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href:self.links.append((self.href,' '.join(self.text)));self.href=None;self.text=[]
def discover(spec):
    url=spec['discovery_url']
    for hop in range(2):
        raw,final=fetch(url);parser=Links();parser.feed(raw.decode('utf-8',errors='replace'))
        choices=sorted({urljoin(final,h) for h,t in parser.links if re.search(spec['anchor_pattern'],t,re.I)})
        pdfs=[u for u in choices if urlsplit(u).path.lower().endswith('.pdf')]
        if len(pdfs)==1:return check_url(pdfs[0])
        if len(choices)==1 and not pdfs:url=check_url(choices[0]);continue
        raise ValueError('No unique approved primary PDF; source requires review')
    raise ValueError('Discovery depth limit reached')
def payload(public,raw):
    parts=[]
    for offset in range(0,len(raw),8*1024*1024):
        block=raw[offset:offset+8*1024*1024];digest=sha256(block).hexdigest();path='blobs/'+digest+'.part';target=public/path
        if target.exists() and target.read_bytes()!=block:raise ValueError('Blob collision')
        target.write_bytes(block);parts.append({'path':path,'bytes':len(block),'sha256':digest})
    return {'bytes':len(raw),'sha256':sha256(raw).hexdigest(),'parts':parts}
def verify_payload(public,item):
    h=sha256();length=0
    for part in item['parts']:
        raw=(public/part['path']).read_bytes()
        if len(raw)!=part['bytes'] or sha256(raw).hexdigest()!=part['sha256']:raise ValueError('Blob verification failed')
        h.update(raw);length+=len(raw)
    if length!=item['bytes'] or h.hexdigest()!=item['sha256']:raise ValueError('Payload verification failed')
def references(text):
    for kind,rx in RX:
        for m in rx.finditer(text):
            value=' '.join(m.group('id').split());prefix=m.groupdict().get('title');citation=kind+':'+((prefix+':') if prefix else '')+value.lower()
            yield {'citation':citation,'kind':kind,'value':value,'literal':m.group(),'start':m.start(),'end':m.end()}
def build(dataset,out):
    out=Path(out)
    if out.exists():raise ValueError('Fresh output directory required')
    out.mkdir(parents=True);public=out/'public';(public/'blobs').mkdir(parents=True);docs=[];gaps=[];texts={}
    specs=json.loads(Path('sources.json').read_text());db=sqlite3.connect(out/'legal.sqlite');db.executescript('CREATE VIRTUAL TABLE laws USING fts5(doc_id UNINDEXED,text); CREATE TABLE links(citation TEXT,record_id TEXT,evidence TEXT); CREATE INDEX reverse_links ON links(citation); CREATE TABLE authorities(id TEXT PRIMARY KEY,metadata TEXT);')
    for spec in specs:
        try:
            url=spec.get('url') or discover(spec);raw,final=fetch(url)
            if not raw.lstrip().startswith(b'%PDF-'):raise ValueError('Expected a primary PDF, not an HTML landing page')
            source=out/(spec['id']+'.pdf');source.write_bytes(raw);textfile=out/(spec['id']+'.txt')
            subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(source),str(textfile)],check=True,timeout=120)
            text=textfile.read_text(encoding='utf-8')
            if len(text.strip())<100:raise ValueError('Extracted text missing; OCR/manual review required')
            doc={**spec,'resolved_url':final,'retrieved_at':datetime.now(timezone.utc).isoformat(),'effective_from':None,'effective_to':None,'historical_applicability':'not_verified','precedential_status':'not_citator_verified' if spec['kind']=='judicial_opinion' else 'not_applicable','original_pdf':payload(public,raw),'extracted_text':payload(public,text.encode('utf-8')),'extraction':'pdftotext layout; original PDF retained; line/page interpretation requires review'}
            docs.append(doc);texts[spec['id']]=text;db.execute('INSERT INTO laws VALUES(?,?)',(spec['id'],text));db.execute('INSERT INTO authorities VALUES(?,?)',(spec['id'],json.dumps(doc)))
        except Exception as e:gaps.append({'source_id':spec['id'],'status':'acquisition_or_extraction_unresolved','reason':type(e).__name__+': '+str(e)[:500],'required':bool(spec.get('required'))})
    dump(public/'acquisition-gaps.json',gaps)
    if any(g['required'] for g in gaps):raise ValueError('Required seed acquisition failed; no legal release published')
    processed=0;edges=0;candidate_edges=0;unresolved=0
    with gzip.open(public/'record-coverage.jsonl.gz','wt',encoding='utf-8') as coverage,gzip.open(public/'crossreferences.jsonl.gz','wt',encoding='utf-8') as links:
        for record in engine.load(dataset):
            count=0
            for ref in references(record['text']):
                candidates=[]
                if ref['kind']=='wy_statute' and ref['value'].startswith('16-') and 'wy-title-16' in texts:
                    positions=[{'start':m.start(),'end':m.end()} for m in re.finditer(r'(?<![0-9])'+re.escape(ref['value'])+r'(?![0-9])',texts['wy-title-16'])]
                    if positions:candidates.append({'authority_id':'wy-title-16','match':'literal text occurrences; may include index or cross-reference, not verified controlling provision','text_occurrences':positions})
                if ref['kind']=='us_case':
                    norm=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
                    for doc in docs:
                        if doc.get('reported_citation') and norm(doc['reported_citation'])==norm(ref['value']):candidates.append({'authority_id':doc['id'],'match':'bibliographic citation candidate; applicability and subsequent treatment unverified'})
                edge={**ref,'record_id':record['id'],'record_version':record['version'],'source_path':record['path'],'span_unit':'zero_based_unicode_code_points_end_exclusive','start_line':record['text'].count('\n',0,ref['start'])+1,'end_line':record['text'].count('\n',0,ref['end'])+1,'context':record['text'][max(0,ref['start']-160):ref['end']+160],'authority_candidates':candidates,'relationship':'explicit_citation_mention','review':'unreviewed','controlling_status':'not_determined','event_date':'not_verified','historical_version_match':'not_verified'}
                links.write(json.dumps(edge,ensure_ascii=False)+'\n');db.execute('INSERT INTO links VALUES(?,?,?)',(ref['citation'],record['id'],json.dumps(edge)));count+=1;edges+=1
                if candidates:candidate_edges+=1
                else:unresolved+=1
            coverage.write(json.dumps({'record_id':record['id'],'record_version':record['version'],'source_path':record['path'],'explicit_citations_detected':count,'status':'explicit_formats_scanned_not_legally_reviewed','gaps':['implicit_frameworks_not_exhaustively_identified','historical_versions_and_controlling_status_unreviewed','lawsuit_names_and_dockets_not_exhaustively_extracted']})+'\n');processed+=1
    if processed!=6065:raise ValueError('Expected all 6065 pinned representations')
    db.commit()
    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Legal index integrity failure')
    db.close();compressed=gzip.compress((out/'legal.sqlite').read_bytes(),mtime=0);index=payload(public,compressed)
    report={'schema':'civic-law-seed-v1','status':'bounded_seed_not_complete_legal_coverage','authorities':docs,'records_scanned':processed,'explicit_citation_edges':edges,'edges_with_seed_candidates':candidate_edges,'unresolved_edges':unresolved,'legal_index_gzip':index,'source_dataset_revision':'2465245db04551c42f748a85fc151b869d246649','source_manifest_sha256':'94b5c51a634350e0e2dec90bde46c59bc1f7bda37c6c8e831354a1aee38077ee','coverage_files':['record-coverage.jsonl.gz','crossreferences.jsonl.gz','acquisition-gaps.json'],'scope_gaps':['municipal code/amendment completeness unverified','county completeness unverified','other state titles and historical versions not ingested','federal statutory/regulatory coverage incomplete','case law and subsequent treatment incomplete','lawsuit docket/filing ingestion not implemented','no legal conclusions or comprehensive implicit-framework detection'],'writes_to_existing_repositories':False}
    dump(public/'collection.json',report)
    for doc in docs:
        verify_payload(public,doc['original_pdf']);verify_payload(public,doc['extracted_text'])
    verify_payload(public,index)
    if any(p.stat().st_size>40*1024*1024 for p in public.rglob('*') if p.is_file()) or size(public)>CAP:raise ValueError('Legal output requires further approved partitioning')
    return report
def publish(out):
    if os.environ.get('GITHUB_REPOSITORY')!=REPO:raise ValueError('Wrong publication repository')
    public=Path(out)/'public';run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
    if not run.isdigit() or not attempt.isdigit():raise ValueError('Invalid run identity')
    target=Path('data')/('run-'+run+'-'+attempt)
    if target.exists() or size('data')+size(public)>CAP:raise ValueError('Immutable generation exists or host capacity exhausted')
    report=json.loads((public/'collection.json').read_text())
    if report['records_scanned']!=6065 or not report['authorities']:raise ValueError('Incomplete legal build')
    shutil.copytree(public,target)
    def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com');git('add',target.as_posix());git('commit','-m','data: isolated legal seed '+run)
    revision=git('rev-parse','HEAD');pointer={'schema':'civic-law-publication-v1','status':report['status'],'revision':revision,'base_url':'https://raw.githubusercontent.com/'+REPO+'/'+revision+'/'+target.as_posix()+'/','collection_sha256':sha256((target/'collection.json').read_bytes()).hexdigest(),'records_scanned':6065,'authorities_stored':len(report['authorities']),'controlling_law_complete':False}
    dump('law-publication.json',pointer);git('add','law-publication.json');git('commit','-m','publish: pin legal seed '+revision)
    for retry in range(3):
        git('fetch','origin','main');git('merge','--no-edit','origin/main')
        if subprocess.run(['git','push','origin','HEAD:main']).returncode==0:return pointer
    raise RuntimeError('Push failed; no forced update attempted')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','publish']);p.add_argument('--dataset-repo');p.add_argument('--out',required=True);a=p.parse_args()
    try:print(json.dumps(build(a.dataset_repo,a.out) if a.command=='build' else publish(a.out),indent=2))
    except Exception as e:
        print('::error::'+(type(e).__name__+': '+str(e)).replace('%','%25').replace('\n','%0A')[:1800],file=sys.stderr);raise
