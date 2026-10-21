from pathlib import Path
from email import policy
from email.parser import BytesParser
from urllib.parse import urljoin, urlsplit
from html import unescape
from bs4 import BeautifulSoup
import base64, re, sys
from io import BytesIO
from PIL import Image
from urllib.parse import urlsplit

src=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/storage/emulated/0/Download/Official Terraria Wiki.mht')
dst=src.with_suffix('.html')
with src.open('rb') as f: msg=BytesParser(policy=policy.default).parse(f)
parts=[p for p in msg.walk() if not p.is_multipart()]
main=next((p for p in parts if p.get_content_type()=='text/html' and (p.get('Content-Location') or '').rstrip('/')=='https://terraria.wiki.gg'),None)
if main is None: main=next(p for p in parts if p.get_content_type()=='text/html')
base=main.get('Content-Location') or 'https://terraria.wiki.gg/'
def decode(p):
 b=p.get_payload(decode=True) or b''
 for enc in (p.get_content_charset(), 'utf-8','windows-1252'):
  if enc:
   try:return b.decode(enc)
   except (LookupError,UnicodeError):pass
 return b.decode('utf-8','replace')
resources={}
for p in parts:
 loc=(p.get('Content-Location') or '').strip()
 if not loc:continue
 if p is main:continue
 resources[unescape(loc)]=p
 if not loc.startswith('cid:'):resources[urljoin(base,unescape(loc))]=p

def lookup(u,origin=base):
 u=unescape(u.strip())
 return resources.get(u) or resources.get(urljoin(origin,u))

bad_images=[]
def datauri(p):
 if p.get_content_type().startswith('image/'):
  raw=p.get_payload(decode=True) or b''
  try:
   im=Image.open(BytesIO(raw));im.load()
  except Exception:
   loc=p.get('Content-Location') or ''
   bad_images.append(loc)
   return loc
 return 'data:'+p.get_content_type()+';base64,'+base64.b64encode(p.get_payload(decode=True) or b'').decode('ascii')

urlpat=re.compile(r'url\(\s*([\'\"]?)(.*?)\1\s*\)',re.I|re.S)
importpat=re.compile(r'@import\s+(?:url\(\s*)?([\'\"])(.*?)\1\s*\)?',re.I)
def css_fix(css,origin,depth=0):
 if depth>4:return css
 def imp(m):
  p=lookup(m.group(2),origin)
  if p and p.get_content_type()=='text/css':
   return css_fix(decode(p),p.get('Content-Location') or origin,depth+1)
  return m.group(0)
 css=importpat.sub(imp,css)
 def rep(m):
  u=m.group(2).strip()
  if u.startswith(('data:','#')):return m.group(0)
  p=lookup(u,origin)
  return 'url("'+datauri(p)+'")' if p else m.group(0)
 return urlpat.sub(rep,css)

soup=BeautifulSoup(decode(main),'html.parser')
for link in list(soup.find_all('link',href=True)):
 if 'stylesheet' not in link.get('rel',[]):continue
 p=lookup(link['href'])
 if p and p.get_content_type()=='text/css':
  style=soup.new_tag('style')
  style.string=css_fix(decode(p),p.get('Content-Location') or base)
  link.replace_with(style)
for tag in soup.find_all(True):
 if tag.has_attr('style'):tag['style']=css_fix(tag['style'],base)
 if tag.name=='style' and tag.string:tag.string.replace_with(css_fix(str(tag.string),base))
 for attr in ('src','poster','data','href','xlink:href'):
  if not tag.has_attr(attr):continue
  if attr=='href' and tag.name not in ('image','use','link'):continue
  p=lookup(tag[attr])
  if p and p.get_content_type() not in ('text/html','text/css'):
   tag[attr]=datauri(p)
 if tag.name=='img':
  tag.attrs.pop('loading',None)
  tag.attrs.pop('decoding',None)
 if tag.has_attr('srcset'):
  # Keep responsive sources intact unless they can be mapped individually.
  candidates=[]
  for candidate in re.split(r',\s+(?=\S)',tag['srcset']):
   bits=candidate.strip().split(None,1)
   if bits:
    p=lookup(bits[0]);bits[0]=datauri(p) if p else bits[0]
    candidates.append(' '.join(bits))
  tag['srcset']=', '.join(candidates)
for meta in soup.find_all('meta',charset=True):meta['charset']='utf-8'
if soup.head and not soup.head.find('meta',charset=True):soup.head.insert(0,soup.new_tag('meta',charset='utf-8'))
dst.write_text(str(soup),encoding='utf-8')
print('Saved:',dst,'Size:',round(dst.stat().st_size/1048576,2),'MB','Resources:',len(resources))

print('Invalid original image parts:',len(set(bad_images)))
