"""Build an attributable, local Wikipedia text/photo cache for the heritage atlas.

Uses public MediaWiki APIs, bounded concurrency, cacheable GETs and retry backoff.
Run again to resume: successful API responses and downloaded images are reused.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'sources/wiki-deps'))
try:
    import requests
except ImportError:
    requests = None
DATA = ROOT / 'dist/data/wikipedia'
IMAGES = ROOT / 'dist/assets/wikipedia'
CACHE = ROOT / 'sources/wiki-cache'
API = 'https://zh.wikipedia.org/w/api.php'
COMMONS = 'https://commons.wikimedia.org/w/api.php'
UA = 'GuanjiHeritageAtlas/1.0 (local cultural-heritage catalogue; Wikimedia API cache)'
TEXT_LICENSE = 'https://creativecommons.org/licenses/by-sa/4.0/'
OVERRIDES_PATH = ROOT/'sources/wikipedia-overrides.json'
OVERRIDES = json.loads(OVERRIDES_PATH.read_text(encoding='utf-8')) if OVERRIDES_PATH.exists() else {}
PRINT_LOCK = threading.Lock()
RATE_LOCK = threading.Lock()
HOST_NEXT = {}
SESSIONS = threading.local()
PAGE_LOCK = threading.Lock()
TITLE_PAGES = None
IMAGE_LOCK = threading.Lock()
IMAGE_PAGES = None
ADMIN = json.loads((ROOT/'dist/data/admin-index.json').read_text(encoding='utf-8'))
COUNTIES = {(p['name'], c['name']): [v['name'] for v in c['counties']] for p in ADMIN for c in p['cities']}

def log(message):
    with PRINT_LOCK:
        print(message, flush=True)

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)

def plain(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()

def request_bytes(url, attempts=4):
    host = urllib.parse.urlparse(url).hostname
    for attempt in range(attempts):
        with RATE_LOCK:
            slot = max(time.monotonic(), HOST_NEXT.get(host, 0))
            HOST_NEXT[host] = slot + (1.2 if host in ('zh.wikipedia.org', 'commons.wikimedia.org') else .4)
        time.sleep(max(0, slot-time.monotonic()))
        try:
            if requests:
                if not hasattr(SESSIONS, 'session'):
                    SESSIONS.session = requests.Session()
                    SESSIONS.session.headers.update({'User-Agent': UA, 'Accept': '*/*'})
                    if os.environ.get('SSL_CERT_FILE'):
                        SESSIONS.session.verify = os.environ['SSL_CERT_FILE']
                try:
                    response = SESSIONS.session.get(url, timeout=(15, 35))
                except requests.RequestException as error:
                    raise urllib.error.URLError(type(error).__name__) from error
                if response.status_code >= 400:
                    raise urllib.error.HTTPError(url, response.status_code, response.reason, response.headers, None)
                return response.content, response.headers.get('Content-Type', '').split(';')[0].strip()
            request = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
            with urllib.request.urlopen(request, timeout=35) as response:
                return response.read(), response.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == attempts - 1:
                raise
            retry = error.headers.get('Retry-After', '') if isinstance(error, urllib.error.HTTPError) else ''
            delay = int(retry) if retry.isdigit() else 30 if isinstance(error, urllib.error.HTTPError) and error.code == 429 else 2 ** (attempt + 1)
            with RATE_LOCK:
                HOST_NEXT[host] = max(HOST_NEXT.get(host, 0), time.monotonic()+delay)

def api(params, endpoint=API):
    params = {'format': 'json', 'formatversion': 2, 'maxlag': 5, **params}
    key = hashlib.sha256((endpoint + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = CACHE / (key + '.json')
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    url = endpoint + '?' + urllib.parse.urlencode(params)
    for attempt in range(4):
        payload, _ = request_bytes(url)
        result = json.loads(payload)
        if 'error' not in result:
            save_json(path, result)
            return result
        if result['error'].get('code') not in ('maxlag', 'ratelimited') or attempt == 3:
            raise RuntimeError(result['error'])
        time.sleep(5 * (attempt + 1))

def chunks(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]

def cached_title_pages():
    global TITLE_PAGES
    with PAGE_LOCK:
        if TITLE_PAGES is None:
            pages={};aliases={}
            for path in CACHE.glob('*.json'):
                try:query=json.loads(path.read_text(encoding='utf-8')).get('query',{})
                except (ValueError,OSError,AttributeError,TypeError):continue
                found=False
                for page in query.get('pages',[]):
                    if page.get('ns',0)==0 and ('extract' in page and 'canonicalurl' in page or page.get('missing') and 'fullurl' in page):
                        pages[page['title']]=page;found=True
                if found:
                    aliases.update({p['from']:p['to'] for key in ('normalized','converted','redirects') for p in query.get(key,[])})
            for alias in aliases:
                title=alias;seen=set()
                while title in aliases and title not in seen:
                    seen.add(title);title=aliases[title]
                if title in pages:pages[alias]=pages[title]
            TITLE_PAGES=pages
        return TITLE_PAGES

def get_pages(titles):
    cached=cached_title_pages()
    known={title:cached[title] for title in titles if title in cached}
    titles=[title for title in titles if title not in known]
    if not titles:return known
    params = {'action': 'query', 'titles': '|'.join(titles), 'redirects': 1,
                  'converttitles': 1, 'variant': 'zh-cn', 'prop': 'extracts|pageimages|info|coordinates|pageprops',
                  'exintro': 1, 'explaintext': 1, 'exlimit': 20, 'piprop': 'name', 'pilicense': 'free',
                  'pilimit': 50, 'inprop': 'url', 'colimit': 'max', 'coprimary': 'primary'}
    if len(urllib.parse.urlencode(params)) > 6500 and len(titles) > 1:
        mid = len(titles)//2
        return {**known, **get_pages(titles[:mid]), **get_pages(titles[mid:])}
    result = api(params)
    query = result.get('query', {})
    pages = {p['title']: p for p in query.get('pages', [])}
    redirects = {p['from']: p['to'] for key in ('normalized', 'converted', 'redirects') for p in query.get(key, [])}
    output = {}
    for title in titles:
        current, seen = title, set()
        while current in redirects and current not in seen:
            seen.add(current)
            current = redirects[current]
        output[title] = pages.get(current, {'title': current, 'missing': True})
    with PAGE_LOCK:TITLE_PAGES.update(output)
    return {**known, **output}

def distance_km(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    d = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(d)))

def normalized(value):
    return re.sub(r'[\s·・（）()，,、—－\-＂“”"]', '', value).replace('造象','造像')

def article_names(row):
    names = [row['name'], *(row.get('aliases') or [])]
    if OVERRIDES.get(row.get('id'),{}).get('title'):
        names.insert(0,OVERRIDES[row['id']]['title'])
    for name in list(names):
        main = re.split(r'[（(]',name)[0]
        if main != name and len(main)>=3:
            names.append(main)
        for alias in re.findall(r'[（(]([^（）()]+)[）)]',name):
            if len(alias)>=3 and not any(word in alias for word in ('包括','含','部分','等')):
                names.append(alias)
        if name.startswith('万里长城－'):
            names.append(name.split('－',1)[1])
        if name.endswith('大殿') and len(name)>4:
            names.append(name[:-2])
        for place in (row.get('city',''),row.get('county','')):
            place = re.sub(r'(市|县|区)$','',place)
            if len(place)>=2 and name.startswith(place) and len(name)-len(place)>=3:
                names.append(name[len(place):])
        if '造象' in name:
            names.append(name.replace('造象','造像'))
    return list(dict.fromkeys(names))

def match_reason(row, page):
    if page.get('missing') or page.get('invalid') or page.get('ns', 0) != 0:
        return None
    if 'disambiguation' in page.get('pageprops', {}) or not page.get('extract', '').strip():
        return None
    text = page.get('extract', '')
    title = page.get('title', '')
    if any(word in title for word in ('列表', '名录', '文物保护单位')):
        return None
    reviewed=OVERRIDES.get(row.get('id'),{})
    if title in reviewed.get('rejectedTitles',[]):
        return None
    if reviewed.get('reviewedRevisionId')==page.get('lastrevid') and reviewed.get('title')==title and reviewed.get('reviewedReason'):
        return reviewed['reviewedReason']
    names = article_names(row)
    name_match = any(normalized(n) in normalized(title) or normalized(n) in normalized(text[:800]) for n in names if len(n) >= 2)
    if not name_match:
        return None
    batch=re.search(r'第([一二三四五六七八])批全国重点文物保护单位',text)
    core=re.split(r'\s*[（(]',title)[0]
    if batch and row.get('batch') and len(row['name'])<=4 and core.endswith(row['name']) and core!=row['name'] and '一二三四五六七八'.index(batch[1])+1!=row['batch']:
        return None
    county = row.get('county', '')
    siblings = COUNTIES.get((row.get('province'), row.get('city')), [])
    if county in siblings and county not in text and any(other != county and other in text for other in siblings):
        return None
    coords = page.get('coordinates', [])
    # A nearby coordinate is strong corroboration; far-away homonyms must be rejected.
    if coords and row.get('coordinates'):
        distance = distance_km(row['coordinates'], [coords[0]['lon'], coords[0]['lat']])
        if distance > 70:
            return None
        if distance <= 25:
            return '名称与地理坐标一致'
    # Require place evidence rather than accepting a name-only match.
    places = [row.get('county', ''), row.get('city', '')]
    places = [p for p in places if p and p not in ('待核对', '跨市', '跨区县')]
    if not places:
        places = [row.get('province', '')]
    for place in places:
        variants = [place, re.sub(r'(自治县|自治州|地区|市|县|区)$', '', place)]
        if any(len(v) >= 2 and v in text for v in variants):
            return '名称与所在地一致'
    return None

def excerpt(text, limit=1400):
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    if len(text) <= limit:
        return text, False
    end = max(text.rfind(mark, 0, limit) for mark in ('。', '！', '？'))
    return text[:end+1 if end >= limit//2 else limit].strip(), True

def image_metadata(names, width=800):
    global IMAGE_PAGES
    with IMAGE_LOCK:
        if IMAGE_PAGES is None:
            IMAGE_PAGES={}
            for path in CACHE.glob('*.json'):
                try:query=json.loads(path.read_text(encoding='utf-8')).get('query',{})
                except (ValueError,OSError,AttributeError,TypeError):continue
                for page in query.get('pages',[]):
                    info=(page.get('imageinfo') or [{}])[0]
                    if page.get('ns')==6 and info.get('extmetadata') and info.get('thumburl') and info.get('thumbwidth',9999)<=480:
                        IMAGE_PAGES[page['title'].removeprefix('File:').replace('_',' ')]=page
        known={name.replace('_',' '):IMAGE_PAGES[name.replace('_',' ')] for name in names if width<=480 and name.replace('_',' ') in IMAGE_PAGES}
    names=[name for name in names if name.replace('_',' ') not in known]
    if not names:return known
    params = {'action': 'query', 'titles': '|'.join('File:' + n for n in names), 'redirects': 1,
              'prop': 'imageinfo', 'iiprop': 'url|extmetadata|mime|size|thumbmime', 'iiurlwidth': width,
              'iiextmetadatalanguage': 'zh', 'iiextmetadatafilter': 'Artist|Credit|LicenseShortName|LicenseUrl|ImageDescription|Copyrighted|Restrictions'}
    if len(urllib.parse.urlencode(params)) > 6500 and len(names) > 1:
        mid = len(names)//2
        return {**known, **image_metadata(names[:mid],width), **image_metadata(names[mid:],width)}
    result = api(params, COMMONS)
    query = result.get('query', {})
    pages = {p['title']: p for p in query.get('pages', [])}
    aliases = {p['from']: p['to'] for key in ('normalized', 'redirects') for p in query.get(key, [])}
    output = {}
    for name in names:
        title, seen = 'File:' + name, set()
        while title in aliases and title not in seen:
            seen.add(title)
            title = aliases[title]
        output[name.replace('_', ' ')] = pages.get(title, {})
    with IMAGE_LOCK:
        if width<=480:IMAGE_PAGES.update(output)
    return {**known,**output}

def store_image(name, page):
    info = (page.get('imageinfo') or [{}])[0]
    meta = info.get('extmetadata', {})
    value = lambda key: plain(meta.get(key, {}).get('value'))
    license_name = value('LicenseShortName')
    license_url = value('LicenseUrl')
    if license_url.startswith('//'):
        license_url = 'https:' + license_url
    author = value('Artist') or value('Credit')
    if not license_name or not author:
        return None
    # Commons metadata is retained verbatim as plain text; no remote HTML is inserted in the UI.
    if info.get('thumburl') and info.get('thumbwidth', 0) > 480:
        mobile = image_metadata([name], 320).get(name.replace('_',' '), {})
        info = (mobile.get('imageinfo') or [info])[0]
    use_original = not info.get('thumburl')
    url = info.get('url') if use_original else info.get('thumburl') or info.get('url')
    if not url or urllib.parse.urlparse(url).hostname not in ('upload.wikimedia.org', 'thumb.wikimedia.org'):
        return None
    # Keep the API-provided standard thumbnail path; tracking parameters are not part of the image.
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(parsed.query) if not k.startswith('utm_')])
    url = urllib.parse.urlunsplit(parsed._replace(query=query))
    mime = info.get('mime', '') if use_original else info.get('thumbmime') or info.get('mime', '')
    extension = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(mime)
    if not extension:
        return None
    filename = hashlib.sha256(name.encode()).hexdigest()[:24] + extension
    path = IMAGES / filename
    if not path.exists():
        content, received_type = request_bytes(url, attempts=2)
        if received_type not in ('image/jpeg', 'image/png', 'image/webp') or len(content) < 100:
            raise ValueError('Image endpoint did not return an image')
        temp = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
        temp.write_bytes(content)
        temp.replace(path)
    return {'path': 'assets/wikipedia/' + filename, 'title': name, 'sourceUrl': info['descriptionurl'],
            'originalUrl': info.get('url'), 'author': author, 'license': license_name, 'licenseUrl': license_url,
            'caption': value('ImageDescription'), 'width': info.get('width') if use_original else info.get('thumbwidth', info.get('width')),
            'height': info.get('height') if use_original else info.get('thumbheight', info.get('height'))}

def search_candidate(row):
    result = api({'action': 'query', 'list': 'search', 'srsearch': 'intitle:"' + row['name'] + '"',
                  'srnamespace': 0, 'srlimit': 5, 'srprop': ''})
    titles = [p['title'] for p in result.get('query', {}).get('search', [])]
    if not titles:
        return None
    for page in get_pages(titles).values():
        reason = match_reason(row, page)
        if reason:
            return page, reason
    return None

def candidate_titles(row):
    locations = [row.get('province'), row.get('county'), re.sub(r'(市|县|区)$','',row.get('county','')), re.sub(r'(市|地区)$','',row.get('city',''))]
    locations = list(dict.fromkeys(p for p in locations if p and p not in ('待核对','跨市','跨区县')))
    names = article_names(row)
    candidates = [name for name in names if name != row['name']]
    candidates.extend(f'{name} ({place})' for name in names for place in locations)
    path=DATA/(row['id']+'.json')
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8'))
        if previous.get('status')=='ready':candidates.insert(0,previous['title'])
    return list(dict.fromkeys(candidates))

def photo_allowed(record_id, image):
    if not image:return True
    override=OVERRIDES.get(record_id,{})
    rejected=override.get('rejectedImages',[])
    if image.get('title','').replace('_',' ') in {name.replace('_',' ') for name in rejected}:return False
    subject=override.get('imageSubject')
    return not subject or subject in image.get('title','')+' '+image.get('caption','')

def article_record(row, page, reason, stamp, image=None):
    text, shortened = excerpt(page['extract'])
    item = {'id': row['id'], 'name': row['name'], 'retrievedAt': stamp,
            'status': 'ready', 'title': page['title'], 'text': text, 'shortened': shortened,
            'sourceUrl': page['canonicalurl'], 'revisionId': page['lastrevid'],
            'revisionUrl': 'https://zh.wikipedia.org/w/index.php?oldid=' + str(page['lastrevid']),
            'license': 'CC BY-SA 4.0', 'licenseUrl': TEXT_LICENSE,
            'authors': '维基百科贡献者', 'matchEvidence': reason, 'image': image if photo_allowed(row['id'],image) else None}
    path=DATA/(row['id']+'.json')
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8'))
        if previous.get('textScope')=='body-excerpt' and previous.get('title')==page['title'] and previous.get('revisionId')==page['lastrevid']:
            item.update(text=previous['text'],shortened=True,textScope='body-excerpt')
            if previous.get('editorialNotes'):item['editorialNotes']=previous['editorialNotes']
    return item

def catalogue_record(row, stamp):
    place = row.get('address') or '、'.join(dict.fromkeys(p for p in (row.get('province'), row.get('city'), row.get('county')) if p and p not in ('待核对', '跨市', '跨区县')))
    era = row.get('era')
    batch = '一二三四五六七八'[row['batch']-1]
    text = f"{row['name']}位于{place}，是全国重点文物保护单位。"
    text += f"名录记载的时代为{era}，" if era and era not in ('不详','未知') else ''
    text += f"文物类型为{row['category']}，本条按第{batch}批名录收录。"
    return {'id':row['id'],'name':row['name'],'title':row['name'],'status':'catalogue',
            'text':text,'sourceUrl':row['source'],'sourceName':'公布名录','retrievedAt':stamp,'image':None}

def save_article(row, page, reason, stamp):
    path = DATA/(row['id']+'.json')
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    image = previous.get('image') if previous.get('title') == page['title'] else None
    save_json(path, article_record(row, page, reason, stamp, image))

def collect_images(names, workers, failures, assignments=None):
    metadata = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks = {pool.submit(image_metadata, batch, 320): batch for batch in chunks(names, 40)}
        for i, future in enumerate(as_completed(tasks), 1):
            try:
                metadata.update(future.result())
            except Exception as error:
                failures.append({'stage': 'image_metadata', 'files': tasks[future], 'error': str(error)})
            if i % 10 == 0 or i == len(tasks):
                log(f'Photo metadata: {i}/{len(tasks)} batches')
    images = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks = {pool.submit(store_image, name, metadata.get(name.replace('_', ' '), {})): name for name in names}
        for i, future in enumerate(as_completed(tasks), 1):
            name = tasks[future]
            try:
                result = future.result()
                if result:
                    images[name] = result
                    for entry_id in (assignments or {}).get(name, []):
                        if not photo_allowed(entry_id,result):continue
                        path = DATA/(entry_id+'.json')
                        if path.exists():
                            item = json.loads(path.read_text(encoding='utf-8'))
                            item['image'] = result
                            save_json(path, item)
            except Exception as error:
                failures.append({'stage': 'image', 'file': name, 'error': str(error)})
                if sum(f.get('stage') == 'image' for f in failures) <= 3:
                    log('Photo download error: ' + str(error)[:160])
            if i % 50 == 0 or i == len(tasks):
                log(f'Local photos: {i}/{len(tasks)} processed, {len(images)} saved')
    return images

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--search-missing', action='store_true')
    parser.add_argument('--deep-search', action='store_true', help='Also run individual full-text searches after batched place-name variants')
    args = parser.parse_args()
    for path in (DATA, IMAGES, CACHE):
        path.mkdir(parents=True, exist_ok=True)
    rows = json.loads((ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    rows.sort(key=lambda r: (r['id'] != 'wb-8-406', r['name'] != '佛光寺'))
    if args.limit:
        rows = rows[:args.limit]
    base_titles = [n for r in rows for n in [r['name'], *(r.get('aliases') or [])]]
    titles = list(dict.fromkeys(n for n in [*base_titles, *(n for r in rows for n in article_names(r))] if n and '|' not in n))
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    pages, failures = {}, []
    rows_by_title = {}
    for row in rows:
        for name in article_names(row):
            rows_by_title.setdefault(name, []).append(row)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks = {pool.submit(get_pages, batch): batch for batch in chunks(titles, 20)}
        for i, future in enumerate(as_completed(tasks), 1):
            try:
                batch_pages = future.result()
                pages.update(batch_pages)
                for name, page in batch_pages.items():
                    for row in rows_by_title.get(name, []):
                        reason = match_reason(row, page)
                        if reason:
                            save_article(row, page, reason, stamp)
            except Exception as error:
                failures.append({'stage': 'article', 'titles': tasks[future], 'error': str(error)})
                log('Article batch error: ' + str(error)[:180])
            if i % 10 == 0 or i == len(tasks):
                log(f'Articles: {i}/{len(tasks)} batches, {len(pages)} titles, {len(failures)} errors')
    matched, unmatched = {}, []
    for row in rows:
        for name in article_names(row):
            page = pages.get(name, {})
            reason = match_reason(row, page)
            if reason:
                matched[row['id']] = (page, reason)
                break
        else:
            unmatched.append(row)
    log(f'Exact title matches: {len(matched)}/{len(rows)}; checking alternatives: {args.search_missing}')
    initial_names = list(dict.fromkeys(p['pageimage'] for p, _ in matched.values() if p.get('pageimage')))
    assignments = {}
    for record_id, (page, _) in matched.items():
        if page.get('pageimage'):
            assignments.setdefault(page['pageimage'], []).append(record_id)
    photo_pool = ThreadPoolExecutor(max_workers=1)
    photo_future = photo_pool.submit(collect_images, initial_names, args.workers, failures, assignments)
    if args.search_missing:
        candidate_map = {row['id']:candidate_titles(row) for row in unmatched}
        all_candidates = list(dict.fromkeys(title for titles in candidate_map.values() for title in titles))
        candidate_pages = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks = {pool.submit(get_pages,batch):batch for batch in chunks(all_candidates,20)}
            for i,future in enumerate(as_completed(tasks),1):
                try:candidate_pages.update(future.result())
                except Exception as error:failures.append({'stage':'candidate','titles':tasks[future],'error':str(error)})
                if i%20==0 or i==len(tasks):log(f'Alternative titles: {i}/{len(tasks)} batches')
        for row in unmatched:
            for title in candidate_map[row['id']]:
                page=candidate_pages.get(title,{})
                reason=match_reason(row,page)
                if reason:
                    matched[row['id']]=(page,reason)
                    save_article(row,page,reason,stamp)
                    break
        log(f'Confirmed articles after place-name variants: {len(matched)}')
    if args.deep_search:
        unmatched=[row for row in rows if row['id'] not in matched]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks = {pool.submit(search_candidate, row): row for row in unmatched}
            for i, future in enumerate(as_completed(tasks), 1):
                row = tasks[future]
                try:
                    found = future.result()
                    if found:
                        matched[row['id']] = found
                        save_article(row, *found, stamp)
                except Exception as error:
                    failures.append({'stage': 'search', 'id': row['id'], 'error': str(error)})
                if i % 50 == 0 or i == len(tasks):
                    log(f'Alternatives: {i}/{len(tasks)}, {len(matched)} confirmed articles')
    names = list(dict.fromkeys(p['pageimage'] for p, _ in matched.values() if p.get('pageimage')))
    images = photo_future.result()
    photo_pool.shutdown()
    assignments = {}
    for record_id, (page, _) in matched.items():
        if page.get('pageimage'):
            assignments.setdefault(page['pageimage'], []).append(record_id)
    missing_images = [name for name in names if name not in images]
    if missing_images:
        images.update(collect_images(missing_images, args.workers, failures, assignments))
    stats = {'total': len(rows), 'withText': len(rows), 'withWikipediaText': 0, 'withPhoto': 0, 'unmatched': 0, 'errors': len(failures)}
    for row in rows:
        found = matched.get(row['id'])
        item = catalogue_record(row, stamp)
        if found:
            page, reason = found
            item = article_record(row, page, reason, stamp, images.get(page.get('pageimage')))
            stats['withWikipediaText'] += 1
        else:
            stats['unmatched'] += 1
        if not item.get('image') and (DATA/(row['id']+'.json')).exists():
            previous = json.loads((DATA/(row['id']+'.json')).read_text(encoding='utf-8'))
            if photo_allowed(row['id'],previous.get('image')):item['image'] = previous.get('image')
        stats['withPhoto'] += bool(item.get('image'))
        save_json(DATA / (row['id'] + '.json'), item)
    save_json(DATA/'index.json', {'generatedAt': stamp, 'stats': stats, 'source': API})
    save_json(ROOT/'wikipedia-audit.json', {'generatedAt': stamp, 'stats': stats, 'errors': failures,
                                         'unmatched': [{'id':r['id'],'name':r['name']} for r in rows if r['id'] not in matched]})
    log('Completed: ' + json.dumps(stats))

if __name__ == '__main__':
    main()
