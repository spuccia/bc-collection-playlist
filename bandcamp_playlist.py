#!/usr/bin/env python3
"""
Extract audio playlists from a Bandcamp user's collection.
Automatically fetches data given a username.

Usage:
    python bandcamp_playlist.py smadicriss
    python bandcamp_playlist.py smadicriss -f m3u
    python bandcamp_playlist.py smadicriss --all-pages -f json -o full.json
"""

import json
import sys
import argparse
import urllib.request
import urllib.parse
from html import unescape
from html.parser import HTMLParser


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"
)

COLLECTION_API_URL = "https://bandcamp.com/api/fancollection/1/collection_items"
WISHLIST_API_URL = "https://bandcamp.com/api/fancollection/1/wishlist_items"
TRALBUM_DETAILS_API_URL = "https://bandcamp.com/api/mobile/25/tralbum_details"


class PageDataExtractor(HTMLParser):
    """Extracts the data-blob content from the #pagedata div."""
    def __init__(self):
        super().__init__()
        self.data_blob = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if attrs_dict.get('id') == 'pagedata' and 'data-blob' in attrs_dict:
            self.data_blob = unescape(attrs_dict['data-blob'])


def http_get(url):
    """Perform a GET request with User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8')


def http_post_json(url, data):
    """Perform a POST JSON request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_initial_page(username):
    """Fetch the profile page and extract the data blob."""
    url = f"https://bandcamp.com/{username}"
    print(f"Fetching page: {url}", file=sys.stderr)
    html = http_get(url)

    parser = PageDataExtractor()
    parser.feed(html)

    if not parser.data_blob:
        print("Error: #pagedata div with data-blob not found.", file=sys.stderr)
        print("The user may not exist or the page structure has changed.", file=sys.stderr)
        sys.exit(1)

    return json.loads(parser.data_blob)


def fetch_all_collection_pages(fan_id, last_token, total_count, section='collection'):
    """Use the pagination API to fetch all tracks beyond the initial batch."""
    api_url = COLLECTION_API_URL if section == 'collection' else WISHLIST_API_URL
    all_tracklists = {}
    page = 1

    while last_token:
        print(f"  Page {page} ({section})... token: {last_token[:30]}...", file=sys.stderr)
        data = {
            "fan_id": fan_id,
            "older_than_token": last_token,
            "count": 20,
        }

        try:
            resp = http_post_json(api_url, data)
        except Exception as e:
            print(f"  API error: {e}", file=sys.stderr)
            break

        items = resp.get("items", [])
        tracklists = resp.get("tracklists", {})
        last_token = resp.get("last_token")

        # Merge tracklists
        for key, tracks in tracklists.items():
            all_tracklists[key] = tracks

        if not items or not last_token:
            break

        page += 1

    return all_tracklists


def fetch_full_album_tracks(band_id, tralbum_id, tralbum_type):
    """
    Fetch the complete tracklist for a single collection/wishlist item
    (album or track) via the tralbum_details API.

    Returns a list of track dicts in the same shape as the ones found in
    the standard `tracklists` structure (title, artist, duration, id, file),
    or None if the item could not be fetched (e.g. private/removed release).
    """
    data = {
        "band_id": band_id,
        "tralbum_id": tralbum_id,
        "tralbum_type": tralbum_type,
    }
    try:
        resp = http_post_json(TRALBUM_DETAILS_API_URL, data)
    except Exception as e:
        print(f"    Warning: could not fetch full album ({tralbum_type}{tralbum_id}): {e}", file=sys.stderr)
        return None

    band_name = (resp.get("band") or {}).get("name", "")
    raw_tracks = resp.get("tracks") or []

    tracks = []
    for track in raw_tracks:
        stream_url = track.get("streaming_url") or {}
        if isinstance(stream_url, dict):
            stream_url = stream_url.get("mp3-128", "")
        tracks.append({
            "title": track.get("title", ""),
            "artist": track.get("band_name") or band_name,
            "duration": track.get("duration", 0),
            "id": track.get("track_id"),
            "file": {"mp3-128": stream_url} if stream_url else {},
        })
    return tracks


def expand_tracklists_to_full_albums(tracklists, item_lookup, section_name):
    """
    Given a batch tracklist (1 track per item) and a lookup of item metadata
    (band_id/tralbum_id/tralbum_type per item key), replace each album entry
    with its complete tracklist fetched from the tralbum_details API.

    This only applies to the batch of items passed in (i.e. it is meant to
    be used on a single page/batch, not across full pagination).
    """
    expanded = {}
    for key, track_list in tracklists.items():
        item = item_lookup.get(key)
        if not item or item.get("tralbum_type") != "a":
            # Not an album (e.g. a standalone track) or metadata unavailable,
            # keep the original single-track entry.
            expanded[key] = track_list
            continue

        band_id = item.get("band_id")
        tralbum_id = item.get("tralbum_id")
        title = item.get("album_title") or item.get("item_title") or key
        print(f"  Fetching full album: {title}...", file=sys.stderr)
        full_tracks = fetch_full_album_tracks(band_id, tralbum_id, "a")

        expanded[key] = full_tracks if full_tracks else track_list

    return expanded


def build_item_lookup(item_cache_section):
    """
    Build a lookup of "<tralbum_type><tralbum_id>" -> item metadata from the
    `item_cache` section of the pagedata blob (e.g. data['item_cache']['collection']).
    """
    lookup = {}
    if not item_cache_section:
        return lookup
    for key, item in item_cache_section.items():
        lookup[key] = item
    return lookup


def extract_tracks_from_tracklists(tracklists, section_name):
    """Convert tracklists dict into a list of track objects."""
    tracks = []
    for key, track_list in tracklists.items():
        for track_info in track_list:
            track = {
                'title': track_info.get('title', ''),
                'artist': track_info.get('artist', ''),
                'duration': track_info.get('duration', 0),
                'track_id': track_info.get('id'),
                'stream_url': track_info.get('file', {}).get('mp3-128', ''),
                'section': section_name,
            }
            tracks.append(track)
    return tracks


def extract_playlist(username, include_wishlist=False, all_pages=False, full_albums=False):
    """Extract the full playlist for a user."""
    data = fetch_initial_page(username)

    fan_data = data.get('fan_data', {})
    fan_id = fan_data.get('fan_id')
    collection_data = data.get('collection_data', {})
    wishlist_data = data.get('wishlist_data', {})
    tracklists = data.get('tracklists', {})
    item_cache = data.get('item_cache', {})

    total_collection = collection_data.get('item_count', 0)
    total_wishlist = wishlist_data.get('item_count', 0)

    print(f"User: {fan_data.get('name', username)}", file=sys.stderr)
    print(f"Collection: {total_collection} items | Wishlist: {total_wishlist} items", file=sys.stderr)

    # Tracks from the initial batch (embedded in the HTML page)
    collection_tracklists = tracklists.get('collection', {})
    wishlist_tracklists = tracklists.get('wishlist', {})

    initial_count = len(collection_tracklists)
    print(f"Tracks in initial batch (collection): {initial_count}", file=sys.stderr)

    # If requested, expand albums in the initial batch to their full
    # tracklist (only applies to this batch, not to any additional pages
    # fetched below via --all-pages).
    if full_albums:
        if all_pages:
            print("Note: --full-albums only expands the initial batch; "
                  "additional pages fetched via --all-pages will still "
                  "contain a single track per album.", file=sys.stderr)
        collection_item_lookup = build_item_lookup(item_cache.get('collection'))
        collection_tracklists = expand_tracklists_to_full_albums(
            collection_tracklists, collection_item_lookup, 'collection')

        if include_wishlist:
            wishlist_item_lookup = build_item_lookup(item_cache.get('wishlist'))
            wishlist_tracklists = expand_tracklists_to_full_albums(
                wishlist_tracklists, wishlist_item_lookup, 'wishlist')

    # If requested, fetch all pages
    if all_pages and total_collection > initial_count:
        last_token = collection_data.get('last_token')
        if last_token and fan_id:
            print(f"Fetching remaining {total_collection - initial_count} tracks...", file=sys.stderr)
            extra = fetch_all_collection_pages(fan_id, last_token, total_collection, 'collection')
            collection_tracklists.update(extra)
            print(f"Total collection tracks fetched: {len(collection_tracklists)}", file=sys.stderr)

    if include_wishlist and all_pages and total_wishlist > len(wishlist_tracklists):
        last_token = wishlist_data.get('last_token')
        if last_token and fan_id:
            print(f"Fetching full wishlist...", file=sys.stderr)
            extra = fetch_all_collection_pages(fan_id, last_token, total_wishlist, 'wishlist')
            wishlist_tracklists.update(extra)

    # Extract tracks
    tracks = extract_tracks_from_tracklists(collection_tracklists, 'collection')

    if include_wishlist:
        tracks += extract_tracks_from_tracklists(wishlist_tracklists, 'wishlist')

    print(f"Total tracks extracted: {len(tracks)}", file=sys.stderr)
    return tracks


def format_duration(seconds):
    """Convert seconds to mm:ss."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def output_txt(tracks):
    lines = []
    for i, t in enumerate(tracks, 1):
        dur = format_duration(t['duration']) if t['duration'] else '?:??'
        lines.append(f"{i:3d}. {t['artist']} - {t['title']} [{dur}]")
    return '\n'.join(lines)


def output_m3u(tracks):
    lines = ['#EXTM3U', '']
    for t in tracks:
        dur = int(t['duration']) if t['duration'] else -1
        lines.append(f"#EXTINF:{dur},{t['artist']} - {t['title']}")
        lines.append(t['stream_url'])
        lines.append('')
    return '\n'.join(lines)


def output_json(tracks):
    return json.dumps(tracks, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description='Extract a playlist from a Bandcamp user collection'
    )
    parser.add_argument('username', help='Bandcamp username')
    parser.add_argument('--format', '-f', choices=['txt', 'm3u', 'json'], default='txt',
                        help='Output format (default: txt)')
    parser.add_argument('--wishlist', '-w', action='store_true',
                        help='Include wishlist tracks')
    parser.add_argument('--all-pages', '-a', action='store_true',
                        help='Fetch ALL tracks (not just the first batch)')
    parser.add_argument('--full-albums', '-F', action='store_true',
                        help='Expand each album to its full tracklist instead of just '
                             'the single track Bandcamp shows in the collection/wishlist. '
                             'Only applies to the initial batch, not to extra pages '
                             'fetched via --all-pages.')
    parser.add_argument('--output', '-o',
                        help='Output file path (default: playlist-<username>.m3u for m3u, stdout for others)')

    args = parser.parse_args()

    tracks = extract_playlist(
        args.username,
        include_wishlist=args.wishlist,
        all_pages=args.all_pages,
        full_albums=args.full_albums,
    )

    if not tracks:
        print("No tracks found.", file=sys.stderr)
        sys.exit(1)

    formatters = {
        'txt': output_txt,
        'm3u': output_m3u,
        'json': output_json,
    }

    result = formatters[args.format](tracks)

    # Default output filename for m3u
    output_path = args.output
    if not output_path and args.format == 'm3u':
        output_path = f"playlist-{args.username}.m3u"

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"Written {len(tracks)} tracks to {output_path}", file=sys.stderr)
    else:
        print(result)


if __name__ == '__main__':
    main()
