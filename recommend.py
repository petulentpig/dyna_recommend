#!/usr/bin/env python3
"""Dynatrace technology-aware release digest. Python 3.9+, standard library only."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
DOCS = 'https://docs.dynatrace.com/docs'
# Canonical inventory types -> precise release-note aliases. No fuzzy matching.
ALIASES = {
 'JAVA': ['Java', 'JVM', 'OpenJDK'], 'NODE_JS': ['Node.js', 'NodeJS', 'ts-node'],
 'DOTNET': ['.NET', 'ASP.NET', 'ASP.NET Core'], 'PYTHON': ['Python'],
 'GO': ['Golang', 'Go applications', 'Go code', 'Go runtime', 'Go module'],
 'PHP': ['PHP'], 'RUBY': ['Ruby'], 'NGINX': ['NGINX'],
 'APACHE_HTTPD': ['Apache HTTP Server', 'Apache HTTPD'],
 'APACHE_KAFKA': ['Kafka', 'confluent_kafka', 'confuent_kafka'],
 'POSTGRES': ['PostgreSQL', 'Postgres'], 'MYSQL': ['MySQL'], 'MSSQL': ['SQL Server'],
 'ORACLE_DB': ['Oracle Database'], 'MONGODB': ['MongoDB'], 'REDIS': ['Redis'],
 'KUBERNETES': ['Kubernetes', 'K8s'], 'OPENSHIFT': ['OpenShift'],
 'LINUX': ['Linux'], 'WINDOWS': ['Windows'], 'AIX': ['AIX'],
 'SPRING': ['Spring'], 'TOMCAT': ['Tomcat'], 'WEBLOGIC': ['WebLogic'],
 'WEBSPHERE': ['WebSphere'], 'GRPC': ['gRPC'], 'OPENTELEMETRY': ['OpenTelemetry'],
 'CONTAINERD': ['containerd'], 'DOCKER': ['Docker'], 'LIBC': ['libc', 'glibc', 'musl'],
 'APACHE_LOG4J': ['Log4j'], 'KOTLIN': ['Kotlin'], 'SCALA': ['Scala'],
 'OK_HTTP_CLIENT': ['OkHttp'], 'CORE_DNS': ['CoreDNS'], 'DJANGO': ['Django'],
 'EXPRESS': ['Express.js'], 'RAILS': ['Rails'], 'VARNISH_CACHE': ['Varnish', 'Vinyl Cache'],
 'APACHE_CAMEL': ['Apache Camel'], 'GRAPHQL': ['GraphQL'], 'NLOG': ['NLog'],
 'AWS_LAMBDA': ['AWS Lambda', 'Lambda functions'], 'AWS_DYNAMODB': ['DynamoDB'],
 'AWS_EVENTBRIDGE': ['EventBridge'], 'AZURE_FUNCTIONS': ['Azure Function', 'Azure Functions'],
 'AZURE_COSMOS_DB': ['CosmosDB', 'Cosmos DB'], 'AZURE_SERVICE_BUS': ['Azure Service Bus'],
 'IBM_CICS_REGION': ['CICS'], 'IBM_IMS': ['IMS'], 'ANGULAR': ['Angular'],
 'AWS_SQS': ['SQS'], 'AWS_SNS': ['SNS'], 'AZURE_EVENTHUB': ['EventHub', 'Event Hub'],
 'DTWIZ': ['dtwiz'], 'OPENFEATURE': ['OpenFeature'],
 'OTEL_COLLECTOR': ['Dynatrace OpenTelemetry Collector'],
 'RUNTIME_VULNERABILITY_ANALYTICS': ['Runtime Vulnerability Analytics'],
 'SQLITE': ['SQLite'], 'ENVOY': ['Envoy'], 'NETTY': ['Netty'], 'ZERO_MQ': ['ZeroMQ'],
 'JDK_HTTP_SERVER': ['JDK HTTP Server'], 'KOTLIN_COROUTINES': ['Kotlin coroutines'],
 'APACHE_HTTP_CLIENT_SYNC': ['Apache HTTP Client'],
 'RUM': ['RUM JavaScript', 'Real User Monitoring'], 'SESSION_REPLAY': ['Session Replay']
}
NORMALIZE = {'LINUX_SYSTEM':'LINUX','WINDOWS_SYSTEM':'WINDOWS','ASP_NET':'DOTNET',
             'OS_TYPE_LINUX':'LINUX','OS_TYPE_WINDOWS':'WINDOWS','POSTGRE_SQL':'POSTGRES','CLR':'DOTNET','POSTGRESQL':'POSTGRES','SPRING_BOOT':'SPRING','NODEJS':'NODE_JS'}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')

def load(path):
    return json.loads(Path(path).read_text())

def dtctl(config, *args):
    binary = config.get('dtctl') or str(ROOT / '.tools/dtctl')
    if not Path(binary).exists() and 'dtctl' not in config:
        binary = 'dtctl'
    proc = subprocess.run([binary, '--context', config['context'], *args],
                          capture_output=True, text=True, timeout=180)
    if proc.returncode:
        # Never surface verbose HTTP/auth output into reports.
        raise ValueError('dtctl failed for '+args[0]+'. Check auth status and context locally.')
    return json.loads(proc.stdout)

def normalize_environment(value):
    value = value.strip()
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError('Enter the full HTTPS Dynatrace instance URL without credentials, query, or fragment.')
    # Compare host names case-insensitively and ignore a trailing slash/default HTTPS port.
    port = parsed.port
    host = parsed.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    netloc = host if port in (None, 443) else host + ':' + str(port)
    return urlunsplit(('https', netloc, parsed.path.rstrip('/'), '', ''))


def choose_environment(explicit=None):
    if explicit is None:
        if not sys.stdin.isatty():
            raise ValueError('Ask the user for their Dynatrace instance URL, then rerun with --environment URL. No instance is assumed.')
        try:
            explicit = input('Which Dynatrace instance should this run use? Enter the full HTTPS URL: ')
        except EOFError:
            raise ValueError('A Dynatrace instance URL is required.') from None
    return normalize_environment(explicit)


def verify_environment(config, environment):
    expected = normalize_environment(environment)
    contexts = dtctl(config, 'config', 'get-contexts', '--no-agent', '-o', 'json')
    if not isinstance(contexts, list):
        raise ValueError('Could not read dtctl contexts; no account will be queried.')
    matches = [c for c in contexts if c.get('Name') == config['context']]
    if len(matches) != 1:
        raise ValueError('Configured dtctl context was not found. Authenticate the requested instance first.')
    context = matches[0]
    if normalize_environment(context['Environment']) != expected:
        raise ValueError('The requested Dynatrace instance does not match the configured dtctl context. Update local.json or log in to the requested instance; no account was queried.')
    if context.get('SafetyLevel') != 'readonly':
        raise ValueError('Use a readonly dtctl context for this pipeline.')
    return expected


def records_from(envelope, limit):
    if envelope.get('ok') is not True:
        raise ValueError('Dynatrace query did not succeed')
    ctx = envelope.get('context', {})
    result = envelope.get('result', {})
    if ctx.get('has_more') or ctx.get('warnings'):
        raise ValueError('Query reports more results or warnings; refusing a partial inventory')
    if result.get('kind') != 'records':
        raise ValueError('Expected inline records; inspect a spilled result before using it')
    records = result['records']
    if len(records) >= limit:
        raise ValueError('Inventory hit its result limit; increase entity_limit')
    if not records:
        raise ValueError('Empty inventory is not evidence that no technologies are used')
    return records

def rank(records):
    entities, versions = defaultdict(set), defaultdict(set)
    observed, unknown = set(), set()
    missing = 0
    for row in records:
        entity = row['id']
        observed.add(entity)
        techs = list(row.get('technologies') or [])
        if row.get('os_type'):
            techs.append({'type':row['os_type'], 'version':row.get('os_version')})
        if not techs:
            missing += 1
        for tech in techs:
            raw = str(tech.get('type', '')).strip().upper()
            if not raw:
                continue
            canonical = NORMALIZE.get(raw, raw)
            entities[canonical].add(entity)
            if tech.get('version'):
                versions[canonical].add(tech['version'])
            if canonical not in ALIASES:
                unknown.add(canonical)
    if not entities:
        raise ValueError('No technology fields found; validate the query schema')
    ranked = [{'technology':t, 'entity_count':len(ids),
               'prevalence_pct':round(100*len(ids)/len(observed), 2),
               'versions':sorted(versions[t]), 'entity_ids':sorted(ids)} for t, ids in entities.items()]
    ranked.sort(key=lambda r:(-r['entity_count'], r['technology']))
    return {'entities':len(observed), 'without_technologies':missing,
            'unmapped_technologies':sorted(unknown), 'ranked':ranked}

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def text(self):
        return re.sub(r'\s+', ' ', ''.join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()
    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, text):
        self.stack[-1].children.append(text)


def get_page(url):
    if not url.startswith(DOCS+'/whats-new/'):
        raise ValueError('Only official Dynatrace release-note URLs are allowed')
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent':'dyna-recommend/0.1'}), timeout=30) as response:
                if not response.url.startswith(DOCS+'/whats-new/'):
                    raise ValueError('Unexpected release source redirect')
                return response.read(8_000_000).decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt+1)


def release_metadata(html, url):
    dom = DOM(html)
    text = ' '.join(n.text() for n in dom.root.walk() if n.tag == 'span')
    match = re.search(r'Rollout start(?:s)? (?:on )?([A-Z][a-z]{2} \d{1,2}, \d{4})', text)
    if not match:
        raise ValueError('Release page has no recognized rollout date: '+url)
    released = datetime.strptime(match[1], '%b %d, %Y').date().isoformat()
    title = next((n.text() for n in dom.root.walk() if n.tag == 'h1'), '')
    version = re.search(r'\b\d+\.\d+(?:\.\d+)*\b', title)
    if not version:
        raise ValueError('Release page has no recognized version: '+url)
    channel = url.split('/whats-new/', 1)[1].split('/')[0]
    return {'url':url, 'title':title, 'date':released, 'version':version[0],
            'channel':channel, 'sha256':digest(html.encode())}


def parse_release(html, url):
    metadata = release_metadata(html, url)
    title, released = metadata['title'], metadata['date']
    dom = DOM(html)
    items, current, section, active = [], None, '', False
    def flush():
        nonlocal current
        if current:
            current['body'] = '\n'.join(current['body'])
            current['id'] = digest((current['url']+'\n'+current['title']+'\n'+current['body']).encode())[:20]
            items.append(current)
            current = None
    def visit(node):
        nonlocal section, current, active
        if node.tag in {'script','style','nav','footer','header'}:
            return
        if node.tag == 'h1':
            active = True
            return
        if not active:
            for child in node.children:
                if isinstance(child, Node): visit(child)
            return
        if node.tag == 'h2':
            flush()
            section = node.text()
            return
        if node.tag == 'h3':
            flush()
            current = {'title':node.text(), 'body':[], 'section':section,
                       'url':url+'#'+node.attrs.get('id',''), 'release':title, 'date':released}
            return
        if node.tag in {'p','li'} and current:
            text = node.text()
            if 'fix' in section.lower() and node.tag == 'li':
                item = dict(current, title=text, body=text)
                item['id'] = digest((item['url']+'\n'+text).encode())[:20]
                items.append(item)
            else:
                current['body'].append(text)
            return
        for child in node.children:
            if isinstance(child, Node): visit(child)
    visit(dom.root)
    flush()
    items = [i for i in items if i['body']]
    if not items:
        raise ValueError('Release parser found no changes: '+url)
    return dict(metadata, items=items)


def fetch_releases(config, out, today):
    """Discover the highest released sprint in each channel, freshly on every run."""
    pages = []
    channels = config['channels']
    if not channels:
        raise ValueError('Configure at least one release channel')
    for channel in dict.fromkeys(channels):
        if channel not in {'oneagent','saas','activegate'}:
            raise ValueError('Unsupported release channel: '+channel)
        index = get_page(DOCS+'/whats-new/'+channel)
        paths = set(re.findall(r'/whats-new/'+channel+r'/sprint-\d+', index))
        if not paths:
            raise ValueError('No release links found for '+channel)
        paths = sorted(paths, key=lambda p:int(p.rsplit('-',1)[1]), reverse=True)
        for path in paths[:20]:
            url = DOCS+path
            html = get_page(url)
            metadata = release_metadata(html, url)
            if date.fromisoformat(metadata['date']) > today:
                continue
            # A malformed newest release must fail, never silently fall back to an older one.
            page = parse_release(html, url)
            (out/(channel+'-'+path.rsplit('/',1)[1]+'.html')).write_text(html)
            pages.append(page)
            break
        else:
            raise ValueError('No released version found within the discovery limit for '+channel)
    return pages


def mentioned(text):
    found = set()
    for technology, aliases in ALIASES.items():
        for alias in aliases:
            if re.search(r'(?<![\w])'+re.escape(alias)+r'(?![\w])', text, re.I):
                found.add(technology)
                break
    return found


def select(inventory, pages):
    usage = {row['technology']:row['entity_count'] for row in inventory['ranked']}
    included, held, excluded, seen = [], [], [], set()
    for page in pages:
        for note in page['items']:
            identity = (note['title'], note['body'])
            if identity in seen: continue
            seen.add(identity)
            tags = mentioned(note['title']+'\n'+note['body'])
            matched = tags & usage.keys()
            absent = tags-usage.keys()
            item = dict(note, technologies=sorted(tags), matched=sorted(matched), undetected=sorted(absent))
            item['usage_score'] = max((usage[t] for t in matched), default=0)
            if not matched:
                item['reason'] = 'No detected technology match' if tags else 'No recognized technology reference'
                excluded.append(item)
            elif absent:
                item['reason'] = 'Also mentions undetected technologies; applicability requires review'
                held.append(item)
            else:
                related = matched - {'LINUX', 'WINDOWS', 'AIX', 'KUBERNETES', 'OPENSHIFT'}
                evidence = [set(row['entity_ids']) for row in inventory['ranked'] if row['technology'] in related]
                if len(evidence)>1 and not set.intersection(*evidence):
                    item['reason'] = 'Technologies detected on different entities; joint applicability unconfirmed'
                    held.append(item)
                else:
                    included.append(item)
    included.sort(key=lambda n:(-n['usage_score'], -date.fromisoformat(n['date']).toordinal(), n['id']))
    return {'included':included, 'held':held, 'excluded':excluded}


def release_label(page):
    names = {'oneagent':'OneAgent', 'saas':'SaaS', 'activegate':'ActiveGate'}
    if page.get('version') and page.get('channel'):
        return names.get(page['channel'], page['channel'])+' '+page['version']
    return page['title']  # Compatibility with existing review reports.


def email_subject(report):
    releases = '; '.join(release_label(p) for p in report.get('source_pages', []))
    return f"Dynatrace updates — {report['customer']}" + (f" — {releases}" if releases else '')


def technology_label(technology):
    if technology == 'GO':
        return 'Go'
    return ALIASES.get(technology, [technology.replace('_',' ').title()])[0]


def draft_text(config, inventory, selection, today):
    lines = [f"Hello {config['customer']} team,", '',
             f"Latest Dynatrace releases — checked {today.isoformat()} (UTC)", '']
    for page in selection['source_pages']:
        lines.extend([f"• {release_label(page)} — rollout started {page['date']}", f"  {page['url']}"])
    lines.extend(['', 'This update covers the latest released version in each product channel listed above.',
                  'Availability in your environment and version or feature prerequisites may vary.', '',
                  'Technology usage ranking',
                  f"Based on {inventory['entities']} observed process and host entities.",
                  'Rank | Technology | Entities | Prevalence | Matched release items',
                  '-----|------------|----------|------------|----------------------'])
    usage = {row['technology']:dict(row, rank=i) for i,row in enumerate(inventory['ranked'],1)}
    for technology, row in usage.items():
        count = sum(technology in note['matched'] for note in selection['included'])
        lines.append(f"{row['rank']} | {technology_label(technology)} | {row['entity_count']} | {row['prevalence_pct']:.2f}% | {count}")
    lines.extend(['', 'Rank is based on distinct observed entities, highest first; ties are ordered alphabetically by technology identifier.',
                  'Prevalence is the share of all queried entities reporting that technology. Hosts and processes count equally.',
                  'An entity can report multiple technologies, so percentages can exceed 100% in total. This measures deployment presence, not traffic or business importance.',
                  f"{inventory['without_technologies']} entities had no technology metadata. A zero item count means no confirmed match for the selected releases, not that the technology is unused.", '',
                  'Relevant release changes (ordered by technology usage)', ''])
    if not selection['included']:
        lines.append('No confirmed technology matches were found for these latest releases. Please review the coverage report before sending an update.')
    for note in selection['included']:
        techs = '; '.join(f"#{usage[t]['rank']} {technology_label(t)}: {usage[t]['entity_count']} entities ({usage[t]['prevalence_pct']:.2f}%)" for t in sorted(note['matched'], key=lambda t:usage[t]['rank']))
        lines.extend([f"• {note['title']}", f"  Usage ranking: {techs}",
                      f"  {note['release']} — rollout {note['date']}", f"  Details and prerequisites: {note['url']}", ''])
    lines += ['Please review the linked notes before planning changes. Technology detection alone does not confirm that a specific version or feature is affected.', '', 'Best regards,', 'Your Dynatrace team']
    return '\n'.join(lines)+'\n'


def run(config, output, environment):
    environment = verify_environment(config, environment)
    output.mkdir(parents=True, exist_ok=False)
    today = datetime.now(timezone.utc).date()
    discovery = dtctl(config, 'inventory', '-o', 'json', '--no-agent')
    write_json(output/'discovery.json', discovery)
    limit = int(config.get('entity_limit',100000))
    envelope = dtctl(config, 'query', '-f', str(ROOT/'queries/technologies.dql'),
                     '--agent','-o','json','--spill=never','--max-result-records',str(limit))
    records = records_from(envelope, limit)
    write_json(output/'inventory-raw.json', envelope)
    inventory = rank(records)
    sources = output/'sources'
    sources.mkdir()
    pages = fetch_releases(config, sources, today)
    selection = select(inventory, pages)
    report = {'status':'needs_review', 'generated_at':datetime.now(timezone.utc).isoformat(),
              'customer':config['customer'], 'context':config['context'], 'environment':environment,
              'release_selection':'latest_released_per_channel', 'inventory':inventory,
              'source_pages':[{k:v for k,v in p.items() if k!='items'} for p in pages], **selection}
    write_json(output/'review.json', report)
    (output/'email.txt').write_text(draft_text(config,inventory,report,today))
    (output/'email-subject.txt').write_text(email_subject(report)+'\n')
    summary = ['# Release digest review', '', 'Status: needs human review. No email has been sent.', '', f'Dynatrace instance: {environment}', '',
               '| Technology | Distinct entities | Prevalence |', '|---|---:|---:|']
    summary.extend(f"| {r['technology']} | {r['entity_count']} | {r['prevalence_pct']}% |" for r in inventory['ranked'])
    summary.extend(['', f"Inventory: {inventory['entities']} entities; {inventory['without_technologies']} without technology metadata.",
                    'Prevalence is distinct entities with this technology / all queried entities; categories overlap.',
                    'Unmapped inventory technologies: '+', '.join(inventory['unmapped_technologies']), '',
                    f"Draft: {len(selection['included'])} items. Held: {len(selection['held'])}. Excluded: {len(selection['excluded'])}.", '',
                    '## Held for applicability review', ''])
    for n in selection['held']:
        summary.append(f"- [{n['title']}]({n['url']}) — {n['reason']}; undetected: {', '.join(n['undetected']) or 'none'}")
    summary.extend(['', 'Review email.txt against source prerequisites and review.json. Edit the draft as needed.',
                    'Confirm the customer name, recipient, monitored versions, and coverage before export.',
                    'Export requires a named reviewer; send manually from your email client.', ''])
    (output/'review.md').write_text('\n'.join(summary))
    print(f"Draft ready: {output}; {len(selection['included'])} matched, {len(selection['held'])} held")


def approve(run_dir, reviewer, recipient):
    report = load(run_dir/'review.json')
    if not reviewer.strip(): raise ValueError('Reviewer is required')
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', recipient):
        raise ValueError('Provide one recipient email address')
    body = (run_dir/'email.txt').read_text()
    if not body.strip(): raise ValueError('Draft is empty')
    message = EmailMessage(policy=SMTP)
    message['To'] = recipient
    message['Subject'] = email_subject(report)
    message['X-Unsent'] = '1'
    message.set_content(body)
    payload = message.as_bytes()
    (run_dir/'approved.eml').write_bytes(payload)
    write_json(run_dir/'approval.json', {'reviewer':reviewer, 'recipient':recipient,
        'approved_at':datetime.now(timezone.utc).isoformat(), 'draft_sha256':digest(body.encode()),
        'eml_sha256':digest(payload), 'status':'approved_for_manual_send'})
    print('Approved message exported. Open approved.eml in your mail client to send. Nothing has been sent.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    r = commands.add_parser('run')
    r.add_argument('--config', default='local.json')
    r.add_argument('--output', type=Path)
    r.add_argument('--environment', help='User-selected Dynatrace instance HTTPS URL; prompts when interactive')
    a = commands.add_parser('approve')
    a.add_argument('run_dir', type=Path)
    a.add_argument('--reviewer', required=True)
    a.add_argument('--to', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            output = args.output or ROOT/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            environment = choose_environment(args.environment)
            run(load(args.config), output, environment)
        else:
            approve(args.run_dir, args.reviewer, args.to)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
