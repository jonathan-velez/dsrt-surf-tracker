"""Upload the existing public ntfy destination through gh stdin, never argv."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]


def convert(url):
    parsed = urlsplit(url)
    # The deployed local configuration uses ntfy://<public-topic>. Do not
    # silently reinterpret custom-server/authenticated Apprise URLs.
    if (parsed.scheme != 'ntfy' or parsed.username or parsed.password or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment or
            not parsed.netloc or ':' in parsed.netloc):
        raise ValueError('Unsupported Apprise syntax; map this destination explicitly')
    topic = unquote(parsed.netloc)
    if not all(c.isascii() and (c.isalnum() or c in '_-') for c in topic):
        raise ValueError('Invalid public ntfy topic')
    return 'https://ntfy.sh/' + topic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / '.local/watch.json')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    settings = json.loads(args.config.read_text())
    urls = settings.get('notification_urls', [])
    if settings.get('notification_muted', True) or len(urls) != 1:
        raise SystemExit('Expected one enabled pricing destination; no secret changed')
    destination = convert(urls[0])
    if args.check:
        print('One enabled public ntfy pricing destination can be migrated; URL redacted.')
        return
    env = dict(os.environ, GH_CONFIG_DIR=str(ROOT / '.local/github'))
    subprocess.run(['gh', 'secret', 'set', 'PRICING_NTFY_URL', '--repo',
                    'jonathan-velez/dsrt-surf-tracker'], input=destination,
                   text=True, env=env, check=True)
    print('Pricing destination uploaded as PRICING_NTFY_URL; daily alerts remain muted.')


if __name__ == '__main__':
    main()
