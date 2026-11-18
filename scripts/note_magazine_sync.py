#!/usr/bin/env python3
"""Sync featured, writing-room and published end-roll works to note magazines.

Requires macOS, Safari signed into the owner's note account, and Safari's
Develop > Allow JavaScript from Apple Events option. No private note API used.
Featured works keep the original baseline-on-first-run behavior. Writing-room
works are backfilled (five per run) when that channel is initialized.
End-roll works wait for Wednesday 21:00 JST AND the owner's public announcement.
They are then added in one throttled batch, resuming after the last confirmed add.

Keyboard Maestro: Execute Shell Script: /usr/bin/python3 /PATH/note_magazine_sync.py
Cron trigger: 20 1,7,13,19 * * * (JST when macOS timezone is Asia/Tokyo).
--install-endroll installs the additional Wednesday launchd schedule on your Mac.
--check-endroll only reads public data; it never opens Safari or changes state.
"""
import argparse
import html
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, time as clock_time, timedelta, timezone

FEED = 'https://komakikosuke.github.io/shirokuma-bungeibu/data/magazine-eligible.json'
MAGAZINE = 'https://note.com/komaki_kousuke/m/mc02c43cae693'
TARGET = '注目記事｜シロクマ文芸部'
ROOM_FEED = 'https://shirokuma-writing-room.claska.chatgpt.site/api/room/articles'
ROOM_MAGAZINE = 'https://note.com/komaki_kousuke/m/m43afa48b795e'
ROOM_TARGET = '「みんなの部室」で書かれた作品'
ENDROLL_FEED = 'https://komakikosuke.github.io/shirokuma-bungeibu/twenty-credits/data/works.json'
ENDROLL_PAGE = 'https://komakikosuke.github.io/shirokuma-bungeibu/twenty-credits/'
ENDROLL_MAGAZINE = 'https://note.com/komaki_kousuke/m/m47893b257d5a'
ENDROLL_TARGET = '20字小説のエンドロール'
AUTHOR = 'komaki_kousuke'
JST = timezone(timedelta(hours=9))
AGENT_LABEL = 'jp.shirokuma.endroll-magazine'
DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'ShirokumaMagazineSync'
STATE_FILE = DATA_DIR / 'state.json'
ROOM_STATE_FILE = DATA_DIR / 'room-state.json'
ENDROLL_STATE_FILE = DATA_DIR / 'endroll-state.json'
SAFARI_GUARD_FILE = DATA_DIR / 'safari-guard.json'
SAFARI_MARKER = '#shirokuma-magazine-sync'
LOG_FILE = DATA_DIR / 'sync.log'
MAX_PER_RUN = 5
NOTE_URL = re.compile(r'^https://note\.com/[A-Za-z0-9_-]+/n/n[A-Za-z0-9]+$')


def public_json(url):
    separator = '&' if '?' in url else '?'
    req = urllib.request.Request(url + separator + 'v=' + str(int(time.time())),
                                 headers={'User-Agent': 'Mozilla/5.0 (ShirokumaMagazineSync/2.0)',
                                          'Accept': 'application/json', 'Referer': 'https://note.com/'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def validate_endroll(data):
    """Accept only the real, already published Tuesday end-roll dataset."""
    if (not isinstance(data, dict) or data.get('version') != 1
            or data.get('pageStatus') != 'ready' or data.get('sourceHashtag') != '20字小説'
            or not isinstance(data.get('works'), list) or not data['works']):
        raise RuntimeError('End-roll data is not ready; no additions')
    event_date = data.get('eventDate', '')
    try:
        day = datetime.strptime(event_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise RuntimeError('Invalid end-roll event date')
    if day.weekday() != 1 or day.isoformat() != event_date:
        raise RuntimeError('End-roll event must be a Tuesday')
    since = datetime.combine(day, clock_time(19), JST)
    until = datetime.combine(day, clock_time(21), JST)
    release = datetime.combine(day + timedelta(days=1), clock_time(21), JST)
    if data.get('sourceWindow') != {'since': since.isoformat(), 'until': until.isoformat()}:
        raise RuntimeError('Unexpected end-roll submission window')
    works = {}
    for row in data['works']:
        if not isinstance(row, dict):
            raise RuntimeError('Invalid end-roll work')
        url = row.get('url', '')
        key, handle = row.get('key'), row.get('handle')
        published = timestamp(row.get('publishedAt'))
        if (not isinstance(url, str) or not NOTE_URL.fullmatch(url)
                or url != f'https://note.com/{handle}/n/{key}' or url in works
                or row.get('sourceType') != 'extracted'
                or type(row.get('charCount')) is not int or not 19 <= row['charCount'] <= 21
                or published is None or not since <= published < until):
            raise RuntimeError('End-roll contains duplicate, test or invalid works')
        works[url] = dict(row)
    if data.get('sourceSummary', {}).get('extracted') != len(works):
        raise RuntimeError('End-roll work count mismatch')
    return event_date, release, works


def announcement_matches(article, key, release, now):
    """Check full public article data, not a title or truncated feed excerpt."""
    if not isinstance(article, dict):
        return False
    published = timestamp(article.get('publish_at'))
    user = article.get('user') or {}
    if (article.get('key') != key or not isinstance(user, dict)
            or user.get('urlname') != AUTHOR or article.get('status') != 'published'
            or article.get('is_draft') is True or article.get('is_reserved') is True
            or article.get('is_published') is False or article.get('is_limited') is True
            or article.get('price', 0) != 0 or published is None
            or not release <= published <= now
            or published.astimezone(JST).date() != release.date()):
        return False
    body = html.unescape(str(article.get('body') or ''))
    # Match the actual end-roll link, including a link card's data-src attribute.
    links = re.findall(r'https?://[^\s<>"\x27]+', body)
    has_endroll_link = any(
        urllib.parse.urlsplit(link)._replace(query='', fragment='').geturl().rstrip('/')
        == ENDROLL_PAGE.rstrip('/') for link in links)
    text = re.sub(r'<[^>]*>', ' ', body)
    return has_endroll_link and 'エンドロール' in str(article.get('name', '')) + text


def find_announcement(release, now, fetch=public_json):
    for page in range(1, 4):
        payload = fetch(f'https://note.com/api/v2/creators/{AUTHOR}/contents?kind=note&page={page}')
        block = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(block, dict) or not isinstance(block.get('contents'), list):
            raise RuntimeError('Unexpected public author feed; no additions')
        notes = block['contents']
        for note in notes:
            if not isinstance(note, dict):
                continue
            published = timestamp(note.get('publishAt'))
            key = note.get('key', '')
            if (note.get('status') != 'published' or published is None
                    or not release <= published <= now
                    or published.astimezone(JST).date() != release.date()
                    or not isinstance(key, str) or not re.fullmatch(r'n[A-Za-z0-9]+', key)):
                continue
            detail = fetch(f'https://note.com/api/v3/notes/{key}')
            if announcement_matches(detail.get('data'), key, release, now):
                return {'url': f'https://note.com/{AUTHOR}/n/{key}',
                        'publishedAt': published.isoformat()}
        # Pinned old notes may occur first, so do not stop at an old date.
        if not notes or block.get('isLastPage') is True:
            break
    return None


def load_endroll_feed(now=None, fetch=public_json):
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        raise RuntimeError('An explicit timezone is required')
    event_date, release, works = validate_endroll(fetch(ENDROLL_FEED))
    result = {'eventDate': event_date, 'releaseAt': release.isoformat(),
              'workCount': len(works), 'magazineUrl': ENDROLL_MAGAZINE,
              'announcement': None, 'works': {}}
    if now < release:
        return dict(result, status='waiting_for_wednesday_21')
    if now >= release + timedelta(days=7):
        return dict(result, status='stale_endroll')
    announcement = find_announcement(release, now, fetch)
    if announcement is None:
        return dict(result, status='waiting_for_public_announcement')
    magazine = fetch('https://note.com/api/v1/magazines/m47893b257d5a').get('data')
    if (not isinstance(magazine, dict) or magazine.get('key') != 'm47893b257d5a'
            or magazine.get('name') != ENDROLL_TARGET or magazine.get('status') != 'public'
            or magazine.get('magazine_url') != ENDROLL_MAGAZINE
            or (magazine.get('user') or {}).get('urlname') != AUTHOR):
        raise RuntimeError('End-roll magazine identity or name changed; no additions')
    return dict(result, status='released', announcement=announcement, works=works)

SCRIPT = '''on run argv
  set operation to item 1 of argv
  set syncMarker to "#shirokuma-magazine-sync"
  tell application "Safari"
    if operation is "preflight" then
      repeat with candidate in windows
        if (count of tabs of candidate) is 1 then
          set candidateURL to URL of current tab of candidate
          if candidateURL starts with "https://note.com/" then
            return do JavaScript "'ok'" in current tab of candidate
          end if
        end if
      end repeat
      return "no-note-tab"
    end if
    if operation is "open" then
      -- Adopt the previous working window, including one left after a failed run.
      repeat with candidate in windows
        if (count of tabs of candidate) is 1 then
          set candidateURL to URL of current tab of candidate
          if candidateURL ends with syncMarker then return (id of candidate) as text
        end if
      end repeat
      -- Create a blank window before navigation. Do not rely on the front window:
      -- Safari can leave another user's window at the front while it creates one.
      set previousIDs to id of every window
      make new document with properties {URL:("about:blank" & syncMarker)}
      repeat 30 times
        repeat with candidate in windows
          set candidateID to id of candidate
          if previousIDs does not contain candidateID then
            if (URL of current tab of candidate) ends with syncMarker then
              return candidateID as text
            end if
          end if
        end repeat
        delay 0.1
      end repeat
      error "Created working window could not be identified; automatic retries paused"
    end if
    set targetID to (item 2 of argv) as integer
    set targetWindow to first window whose id is targetID
    if operation is "navigate" then
      if (count of tabs of targetWindow) is not 1 then error "Working window has extra tabs"
      if (URL of current tab of targetWindow) does not end with syncMarker then error "Working window marker lost"
      set URL of current tab of targetWindow to ((item 3 of argv) & syncMarker)
      return "ok"
    end if
    if operation is "url" then return URL of current tab of targetWindow
    if operation is "js" then return do JavaScript (item 3 of argv) in current tab of targetWindow
    if operation is "close" then
      if (count of tabs of targetWindow) is not 1 then error "Preserved working window: extra tabs"
      if (URL of current tab of targetWindow) does not end with syncMarker then error "Preserved window: marker lost"
      close targetWindow
      return "ok"
    end if
  end tell
end run'''

# Exact target magazine name and exactly ONE button in its row are required.
# These calls never use note's private APIs; they only interact with visible UI.
JS = r'''(() => {
  const target = %s;
  const text = e => (e?.innerText || e?.textContent || '').trim();
  const visible = e => {
    const s=getComputedStyle(e),r=e.getBoundingClientRect();
    return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
  };
  const buttons = [...document.querySelectorAll('button')]
    .filter(b => visible(b) && /^(追加|追加済|追加する|追加済み)$/.test(text(b)));
  const rows=[];
  for (const button of buttons) {
    let el=button.parentElement;
    for(let d=0;el && d<9;d++,el=el.parentElement) {
      const lines=text(el).split('\n').map(s=>s.trim()).filter(Boolean);
      if (lines.includes(target) && el.querySelectorAll('button').length === 1) {
        rows.push({button,container:el}); break;
      }
    }
  }
  if (rows.length>1) return JSON.stringify({status:'error',message:'multiple magazine rows'});
  if (rows.length===1) {
    const row=rows[0]; const state=text(row.button);
    if (/^追加済/.test(state))return JSON.stringify({status:'already'});
    if (!/^追加/.test(state))return JSON.stringify({status:'error',message:'unknown button status'});
    if (%s === 'add') {row.button.click();return JSON.stringify({status:'clicked'});}
    return JSON.stringify({status:'ready'});
  }
  if (%s === 'open') {
    // Verified note DOM: "記事を追加" is an icon-only ButtonIcon. In the
    // rendered DOM it may have no text, aria-label, or title, so identify the
    // book-plus icon by the observed SVG path instead of its accessible text.
    const bookIcon = b => [...b.querySelectorAll('svg path')].some(p =>
      (p.getAttribute('d') || '').includes('5.493v11.902Z'));
    const displayed = b => {
      const r = b.getBoundingClientRect();
      const st = getComputedStyle(b);
      return r.width > 0 && r.height > 0 && st.visibility !== 'hidden'
        && st.display !== 'none' && !b.disabled;
    };
    const icons=[...document.querySelectorAll('button[data-id="ButtonIcon"]')]
      .filter(b => bookIcon(b) && displayed(b));
    // Responsive layouts can render duplicates; the first visible match is
    // the article-toolbar action, and both matches represent the same action.
    if (!icons.length) return JSON.stringify({status:'error',message:'book-plus icon not found'});
    icons[0].click();
    return JSON.stringify({status:'opened'});
  }
  return JSON.stringify({status:'waiting'});
})()'''


def log(msg):
    s = datetime.now().astimezone().isoformat(timespec='seconds') + ' | ' + msg
    print(s, flush=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(s + '\n')


def applescript(*args):
    try:
        p = subprocess.run(['/usr/bin/osascript', '-e', SCRIPT, *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           timeout=35)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Safari '+args[0]+': AppleScript timed out after 35 seconds')
    if p.returncode:
        raise RuntimeError('Safari '+args[0]+': ' + p.stderr.strip()[:450])
    return p.stdout.strip()


def load_feed():
    req = urllib.request.Request(FEED + '?v=' + str(int(time.time())),
                                 headers={'User-Agent':'ShirokumaMagazineSync/1.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    if data.get('magazineUrl') != MAGAZINE or not isinstance(data.get('works'),list):
        raise RuntimeError('Unexpected magazine-eligible.json format or magazine URL')
    result = {}
    for item in data['works']:
        if not isinstance(item,dict): continue
        url = str(item.get('url','')).split('?')[0].rstrip('/')
        if NOTE_URL.fullmatch(url): result[url] = item
    return result


def load_room_feed():
    """Load all room articles through the public, cursor-paginated endpoint."""
    result = {}
    cursor = None
    seen_cursors = set()
    for _ in range(100):
        params = {'v': str(int(time.time()))}
        if cursor is not None:
            params['cursor'] = cursor
        url = ROOM_FEED + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent':'ShirokumaMagazineSync/1.1'})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
        if not isinstance(data, dict) or not isinstance(data.get('articles'), list):
            raise RuntimeError('Unexpected room articles response')
        for item in data['articles']:
            if not isinstance(item, dict):
                continue
            article_url = str(item.get('url', '')).split('?')[0].rstrip('/')
            shared_at = item.get('sharedAt')
            if NOTE_URL.fullmatch(article_url) and isinstance(shared_at, int) and shared_at >= 0:
                result[article_url] = item
        next_cursor = data.get('nextCursor')
        if next_cursor is None:
            return result
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            raise RuntimeError('Invalid or repeated room article cursor')
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise RuntimeError('Too many room article pages')


def save_state(state, state_file=STATE_FILE):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = state_file.with_suffix('.tmp')
    target.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    target.replace(state_file)


def js(window,action,target=TARGET):
    code = JS % (json.dumps(target,ensure_ascii=False), json.dumps(action),json.dumps(action))
    raw = applescript('js',window,code)
    try:return json.loads(raw)
    except json.JSONDecodeError:raise RuntimeError('Unexpected Safari result: '+raw[:200])


def wait_article(window,url):
    until=time.monotonic()+35
    while time.monotonic()<until:
        try:
            current=urllib.parse.urlsplit(applescript('url',window))._replace(query='',fragment='').geturl().rstrip('/')
            if current==url:
                ready=applescript('js',window,'document.readyState')
                if ready=='complete':return
        except RuntimeError:pass
        time.sleep(1.2)
    raise RuntimeError('Article navigation timed out: '+url)


def process(window,item,target=TARGET):
    url=item['url']
    applescript('navigate',window,url)
    wait_article(window,url)
    deadline=time.monotonic()+25
    opened=False
    while time.monotonic()<deadline:
        status=js(window,'inspect',target)['status']
        if status=='already':return 'already'
        if status=='ready':break
        if status=='error':raise RuntimeError('Unexpected magazine dialog: '+str(js(window,'inspect',target)))
        if not opened:
            result=js(window,'open',target)
            if result['status']=='opened':opened=True
            elif result['status']=='error':
                # Wait briefly for note's client UI to load; stop if still absent.
                if time.monotonic()+5>=deadline:
                    raise RuntimeError(result.get('message','Unable to open magazine dialog'))
        time.sleep(.8)
    else:raise RuntimeError('Magazine dialog not ready')

    result=js(window,'add',target)
    if result['status']=='already':return 'already'
    if result['status']!='clicked':raise RuntimeError('Add click not accepted: '+str(result))
    deadline=time.monotonic()+18
    while time.monotonic()<deadline:
        result=js(window,'inspect',target)
        if result['status']=='already':return 'added'
        if result['status']=='error':raise RuntimeError(str(result))
        time.sleep(.8)
    raise RuntimeError('Clicked add, but note did not confirm added; check magazine before retry')


def _load_state(state_file):
    state=json.loads(state_file.read_text(encoding='utf-8'))
    if state.get('version')!=1 or not isinstance(state.get('seen'),list):
        raise RuntimeError('Unknown local state version, refusing additions: '+state_file.name)
    return state


def _prepare_channel(label, works, state_file, target, baseline_first_run, sort_key,
                     max_per_run=MAX_PER_RUN):
    now=datetime.now(timezone.utc).isoformat()
    if not state_file.exists():
        if baseline_first_run:
            save_state({'version':1,'baselineAt':now,'seen':sorted(works),'added':[],'failures':[]},state_file)
            log(f'[{label}] INITIALIZED: baseline {len(works)} works, no magazine additions')
            return {'label':label,'works':works,'state_file':state_file,'target':target,
                    'state':None,'seen':set(),'added':set(),'pending':[]}
        save_state({'version':1,'initializedAt':now,'seen':[],'added':[],'failures':[]},state_file)
        log(f'[{label}] INITIALIZED: {len(works)} existing works queued for backfill')
    state=_load_state(state_file)
    seen=set(state['seen']);added=set(state.get('added',[]))
    pending=[dict(w,url=url) for url,w in works.items() if url not in seen and url not in added]
    pending.sort(key=sort_key)
    return {'label':label,'works':works,'state_file':state_file,'target':target,
            'state':state,'seen':seen,'added':added,'pending':pending[:max_per_run]}


def prepare_channels(endroll_only=False):
    channels, errors = [], []
    try:
        release = load_endroll_feed()
        log(f"[20字小説] {release['status']}: event {release['eventDate']}, {release['workCount']} works")
        if release['status'] == 'released':
            channel = _prepare_channel('20字小説', release['works'], ENDROLL_STATE_FILE,
                                       ENDROLL_TARGET, False,
                                       lambda w: (w['publishedAt'], w['url']), max_per_run=None)
            channel['state'].update(eventDate=release['eventDate'], releaseAt=release['releaseAt'],
                                    announcement=release['announcement'])
            save_state(channel['state'], ENDROLL_STATE_FILE)
            channels.append(channel)
    except Exception as error:
        errors.append(f'20字小説: {error}')
        log(f'[20字小説] STOP CHANNEL: {error}')
    if not endroll_only:
        for label, loader, state_file, target, baseline, sort_key in [
                ('部室', load_room_feed, ROOM_STATE_FILE, ROOM_TARGET, False,
                 lambda w: (w.get('sharedAt', 0), w['url'])),
                ('注目記事', load_feed, STATE_FILE, TARGET, True,
                 lambda w: (w.get('firstCommentAt', ''), w['url']))]:
            try:
                channels.append(_prepare_channel(label, loader(), state_file, target, baseline, sort_key))
            except Exception as error:
                errors.append(f'{label}: {error}')
                log(f'[{label}] STOP CHANNEL: {error}')
    return channels, errors


def agent_config(script_path):
    # launchd calendar fields use the Mac's local timezone. Installation verifies JST.
    times = [{'Weekday': 3, 'Hour': 21, 'Minute': minute} for minute in (0, 2, 5, 10, 20, 40)]
    times += [{'Weekday': 3, 'Hour': 22, 'Minute': minute} for minute in (0, 30)]
    return {'Label': AGENT_LABEL,
            'ProgramArguments': ['/usr/bin/python3', str(script_path), '--endroll-only'],
            'StartCalendarInterval': times, 'RunAtLoad': True, 'ProcessType': 'Background',
            'StandardOutPath': str(DATA_DIR / 'launchd-endroll.log'),
            'StandardErrorPath': str(DATA_DIR / 'launchd-endroll.log')}


def install_endroll_agent(start_paused=False):
    if sys.platform != 'darwin':
        raise RuntimeError('Install on the Mac that already runs the magazine sync')
    # Calendar triggers are evaluated by launchd, not the child process's TZ setting.
    for day in (datetime(2026, 1, 1), datetime(2026, 7, 1)):
        if day.astimezone().utcoffset() != timedelta(hours=9):
            raise RuntimeError('Set the Mac timezone to Asia/Tokyo before installing')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if start_paused:
        save_state({'status': 'paused', 'stage': 'repair',
                    'at': datetime.now(timezone.utc).isoformat(),
                    'error': 'Paused for diagnosis after unexpected Safari windows'}, SAFARI_GUARD_FILE)
    domain = 'gui/' + str(os.getuid())
    # Stop the old scheduled process before replacing code or registering a new one.
    subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + AGENT_LABEL],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    destination = DATA_DIR / 'note_magazine_sync.py'
    source = Path(__file__).resolve()
    if source != destination.resolve():
        if destination.exists():
            shutil.copy2(destination, destination.with_suffix('.py.bak'))
        temporary = destination.with_suffix('.installing')
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    agents = Path.home() / 'Library' / 'LaunchAgents'
    agents.mkdir(parents=True, exist_ok=True)
    agent = agents / (AGENT_LABEL + '.plist')
    temporary = agent.with_suffix('.tmp')
    temporary.write_bytes(plistlib.dumps(agent_config(destination)))
    temporary.replace(agent)
    registered = subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(agent)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    if registered.returncode:
        raise RuntimeError('Could not register Wednesday schedule: ' + registered.stderr.strip()[:400])
    log('INSTALLED: Wednesday 21:00 JST; Safari error circuit breaker enabled'
        + ('; PAUSED for diagnosis' if start_paused else ''))


def diagnose_endroll():
    """Print local evidence without opening, changing or closing Safari windows."""
    for label, path, limit in [('Safari guard', SAFARI_GUARD_FILE, 20),
                                ('Recent sync.log', LOG_FILE, 40),
                                ('Recent launchd-endroll.log', DATA_DIR / 'launchd-endroll.log', 30)]:
        print(label + ':', flush=True)
        if path.exists():
            print('\n'.join(path.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:])[-14000:])
        else:
            print('(not present)')
    if ENDROLL_STATE_FILE.exists():
        state = _load_state(ENDROLL_STATE_FILE)
        print('End-roll checkpoint: ' + json.dumps(
            {'eventDate': state.get('eventDate'), 'confirmedCount': len(state.get('added', [])),
             'latestFailure': (state.get('failures') or [None])[-1]}, ensure_ascii=False))
    result = load_endroll_feed()
    result.pop('works')
    print('Public release check: ' + json.dumps(result, ensure_ascii=False))


def safari_guard(stage, error=None):
    payload = {'status': 'paused' if error else 'in_progress', 'stage': stage,
               'at': datetime.now(timezone.utc).isoformat()}
    if error is not None:
        payload['error'] = str(error)[:1500]
    save_state(payload, SAFARI_GUARD_FILE)


def main(endroll_only=False, resume_safari=False, max_works=None):
    if sys.platform!='darwin':raise RuntimeError('Only runs on your Mac (macOS)')
    # Prevent overlapping scheduled invocations.
    import fcntl
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    with (DATA_DIR/'run.lock').open('w') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            log('SKIP: another run is active');return
        if SAFARI_GUARD_FILE.exists():
            if not resume_safari:
                log('PAUSED: previous Safari operation needs diagnosis; no windows opened. Use --diagnose-endroll.')
                return
            SAFARI_GUARD_FILE.unlink()
            log('RESUMED: explicit Safari retry requested')
        channels,channel_errors=prepare_channels(endroll_only)
        if max_works is not None:
            budget = max_works
            for channel in channels:
                channel['pending'] = channel['pending'][:budget]
                budget -= len(channel['pending'])
        pending_count=sum(len(channel['pending']) for channel in channels)
        if not pending_count:
            if channel_errors:raise RuntimeError(' / '.join(channel_errors))
            log('OK: no released, unprocessed works');return
        log('Processing '+', '.join(f"{channel['label']} {len(channel['pending'])}" for channel in channels if channel['pending']))
        window=None
        ui_error=None
        stage='preflight'
        safari_guard(stage)
        try:
            log('Safari step: preflight (checking JavaScript permission without creating a window)')
            checked=applescript('preflight')
            if checked not in ('ok','no-note-tab'):
                raise RuntimeError('Unexpected Safari preflight result: '+repr(checked)[:200])
            stage='open';safari_guard(stage)
            log('Safari step: open or reuse the marked working window')
            window=applescript('open')
            if not window.isdigit():raise RuntimeError('Unable to identify dedicated Safari window: '+repr(window)[:200])
            for channel in channels:
                state=channel['state'];seen=channel['seen'];added=channel['added']
                for item in channel['pending']:
                    url=item['url']
                    try:
                        stage='process '+url;safari_guard(stage)
                        log(f"[{channel['label']}] CHECK: {url}")
                        outcome=process(window,item,channel['target'])
                        if outcome not in ('added','already'):
                            raise RuntimeError('Unconfirmed magazine result: '+repr(outcome)[:200])
                        seen.add(url);added.add(url)
                        state['seen']=sorted(seen);state['added']=sorted(added)
                        save_state(state,channel['state_file'])
                        log(f"[{channel['label']}] {outcome.upper()}: {url}")
                    except Exception as e:
                        # Do NOT mark as processed or continue blindly within the
                        # same channel. The other independent channel may proceed.
                        state.setdefault('failures',[]).append({'url':url,'at':datetime.now(timezone.utc).isoformat(), 'error':str(e)[:400]})
                        save_state(state,channel['state_file'])
                        log(f"[{channel['label']}] STOP CHANNEL: {url} / {e}")
                        channel_errors.append(f"{channel['label']}: {e}")
                        ui_error=e
                        safari_guard(stage,e)
                        break
                    time.sleep(5)
                if ui_error is not None:break
        except BaseException as error:
            ui_error=error
            safari_guard(stage,error)
            raise
        finally:
            if window:
                try:
                    if applescript('close',window) != 'ok':
                        raise RuntimeError('Safari did not confirm working-window cleanup')
                except Exception as error:
                    log('PAUSED: could not close Safari sync window: '+str(error))
                    if ui_error is None:
                        ui_error=error
                        channel_errors.append(str(error))
                        safari_guard('close',error)
            if ui_error is None:
                SAFARI_GUARD_FILE.unlink(missing_ok=True)
            else:
                log('PAUSED: automatic Safari retries stopped. Previous confirmations are saved; run --diagnose-endroll.')
        if channel_errors:
            raise RuntimeError(' / '.join(channel_errors))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--endroll-only',action='store_true',help='Run only the gated end-roll channel')
    mode.add_argument('--check-endroll',action='store_true',help='Read-only release and work-count check')
    mode.add_argument('--install-endroll',action='store_true',help='Install Wednesday 21:00 scheduling on macOS')
    mode.add_argument('--repair-endroll',action='store_true',help='Update the Mac code, pause Safari retries and print logs; does not open windows')
    mode.add_argument('--diagnose-endroll',action='store_true',help='Print local logs and public release state without operating Safari')
    parser.add_argument('--resume-safari',action='store_true',help='Explicitly retry once after a paused Safari failure')
    parser.add_argument('--max-works',type=int,help='Limit a manual verification run to this many works')
    args=parser.parse_args()
    if args.max_works is not None and args.max_works < 1:parser.error('--max-works must be positive')
    if args.resume_safari and not args.endroll_only:parser.error('--resume-safari requires --endroll-only')
    try:
        if args.check_endroll:
            result=load_endroll_feed()
            result.pop('works')
            print(json.dumps(result,ensure_ascii=False,indent=2))
        elif args.install_endroll:
            install_endroll_agent()
        elif args.repair_endroll:
            install_endroll_agent(start_paused=True)
            diagnose_endroll()
        elif args.diagnose_endroll:
            diagnose_endroll()
        else:
            main(args.endroll_only,args.resume_safari,args.max_works)
    except Exception as ex:
        if args.check_endroll:print('ERROR: '+str(ex),file=sys.stderr)
        else:log('ERROR: '+str(ex))
        sys.exit(1)
