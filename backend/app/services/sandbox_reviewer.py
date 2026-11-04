"""Trusted reviewer program executed in its own container; never imports candidate code."""

REVIEWER = r'''
import ast,hashlib,json,re,sys
payload=json.load(sys.stdin);findings=[]
for path,source in payload['files'].items():
    if not isinstance(source,str): continue
    for pattern,severity,category in [
        (r'\beval\s*\(|\bexec\s*\(|\bos\.system\s*\(|shell\s*=\s*True','CRITICAL','UNSAFE_EXECUTION'),
        (r'(?i)(password|api_key|secret)\s*[:=]\s*[\x27\x22][^\x27\x22]+','HIGH','SECRET'),
        (r'(?i)\b(TODO|FIXME|NotImplementedError)\b','MEDIUM','INCOMPLETE'),
        (r'(?i)(SELECT|UPDATE|DELETE).*\+','HIGH','SQL_INJECTION')]:
        for match in re.finditer(pattern,source):
            identity=hashlib.sha256((path+category+str(match.start())).encode()).hexdigest()[:24]
            findings.append(dict(finding_id=identity,severity=severity,category=category,path=path,line=source[:match.start()].count('\n')+1,message='Independent reviewer detected '+category))
    if path.endswith('.py'):
        try: ast.parse(source)
        except SyntaxError: findings.append(dict(finding_id=hashlib.sha256(path.encode()).hexdigest()[:24],severity='HIGH',category='SYNTAX',path=path,message='Candidate Python is invalid'))
print(json.dumps(dict(status='REJECTED' if findings else 'PASS',findings=findings,reviewer_version='w09-independent-review-v1',limitations=['Static source review; security/license tools and observed behavior are separately required'])))
'''
