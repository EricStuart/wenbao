"""Check every local introduction and referenced photo; refresh coverage stats."""
from collections import Counter
from datetime import datetime, timezone
import json
import re
import fetch_wikipedia as w


def main():
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    stats={'total':len(rows),'withText':0,'withWikipediaText':0,'withCatalogueText':0,'withPhoto':0}
    errors=[];missing_photos=[];checked_images=set();licenses=Counter()
    for row in rows:
        path=w.DATA/(row['id']+'.json')
        if not path.exists():
            errors.append({'id':row['id'],'error':'missing introduction file'});continue
        try:entry=json.loads(path.read_text(encoding='utf-8'))
        except Exception as error:
            errors.append({'id':row['id'],'error':str(error)});continue
        if entry.get('id')!=row['id'] or entry.get('name')!=row['name']:
            errors.append({'id':row['id'],'error':'record identity mismatch'})
        if not entry.get('text','').strip():
            errors.append({'id':row['id'],'error':'empty text'})
        else:stats['withText']+=1
        if entry.get('status')=='ready':
            stats['withWikipediaText']+=1
            if not all(entry.get(k) for k in ('title','revisionUrl','revisionId','authors','license','licenseUrl','matchEvidence')):
                errors.append({'id':row['id'],'error':'incomplete Wikipedia attribution'})
        elif entry.get('status')=='catalogue':stats['withCatalogueText']+=1
        if not entry.get('sourceUrl','').startswith(('https://','http://')):
            errors.append({'id':row['id'],'error':'missing source link'})
        photo=entry.get('image')
        if not photo:
            missing_photos.append({'id':row['id'],'name':row['name']});continue
        if not w.photo_allowed(row['id'],photo):
            errors.append({'id':row['id'],'error':'photo failed reviewed subject restrictions'})
        relative=photo.get('path','')
        if not re.fullmatch(r'assets/wikipedia/[a-f0-9]+\.(jpg|png|webp)',relative):
            errors.append({'id':row['id'],'error':'invalid local photo path'});continue
        image=w.ROOT/'dist'/relative
        if not image.exists():
            errors.append({'id':row['id'],'error':'missing local photo file'});continue
        if relative not in checked_images:
            with image.open('rb') as handle:header=handle.read(16)
            valid=header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG\r\n\x1a\n') or header[:4]==b'RIFF' and header[8:12]==b'WEBP'
            if not valid or image.stat().st_size<100:
                errors.append({'id':row['id'],'error':'invalid image bytes'})
            checked_images.add(relative)
        if not all(photo.get(k) for k in ('author','license','sourceUrl','title')):
            errors.append({'id':row['id'],'error':'incomplete photo attribution'})
        stats['withPhoto']+=1;licenses[photo['license']]+=1
    stats.update(withoutPhoto=len(missing_photos),uniquePhotoFiles=len(checked_images),errors=len(errors))
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    w.save_json(w.ROOT/'wikipedia-coverage-audit.json',{'generatedAt':stamp,'stats':stats,'errors':errors,'licenses':dict(licenses),'missingPhotos':missing_photos})
    w.save_json(w.DATA/'index.json',{'generatedAt':stamp,'stats':stats,'source':w.API})
    w.log(json.dumps(stats))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
