# bc-collection-playlist

A command-line tool to extract audio playlists from any public Bandcamp user collection.

Given a Bandcamp username, it fetches the user's collection (and optionally their wishlist), then outputs a playlist in M3U, plain text, or JSON format.

## Features

- **Zero dependencies** — uses only Python 3 standard library
- **Automatic pagination** — fetches entire collections, not just the first page
- **Multiple output formats** — M3U (playable in VLC/mpv), plain text, JSON
- **Wishlist support** — optionally include wishlisted tracks
- **Stream URLs included** — M3U files contain direct mp3-128 stream links

## Requirements

- Python 3.6+

## Usage

```bash
# Basic: print first 20 tracks as text
python bandcamp_playlist.py <username>

# Generate M3U playlist (saves to playlist-<username>.m3u)
python bandcamp_playlist.py <username> -f m3u

# Fetch the ENTIRE collection (all pages)
python bandcamp_playlist.py <username> -f m3u --all-pages

# Include wishlist tracks
python bandcamp_playlist.py <username> -f m3u --all-pages --wishlist

# Expand each album to its full tracklist (initial batch only)
python bandcamp_playlist.py <username> -f m3u --full-albums

# Export as JSON
python bandcamp_playlist.py <username> -f json --all-pages -o collection.json

# Custom output path
python bandcamp_playlist.py <username> -f m3u -o my-playlist.m3u
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `username` | | Bandcamp username (required) |
| `--format` | `-f` | Output format: `txt`, `m3u`, or `json` (default: `txt`) |
| `--all-pages` | `-a` | Fetch all collection pages, not just the initial batch of 20 |
| `--full-albums` | `-F` | Expand each album to its full tracklist instead of the single track Bandcamp shows in the collection/wishlist. Only applies to the initial batch — extra pages fetched via `--all-pages` still return one track per album |
| `--wishlist` | `-w` | Include wishlist tracks in the output |
| `--output` | `-o` | Output file path. For M3U format, defaults to `playlist-<username>.m3u` |

## Output Formats

### M3U

Standard extended M3U playlist, playable in VLC, mpv, foobar2000, etc.

```
#EXTM3U

#EXTINF:289,Stones Taro - Odoriko feat. MFS
https://bandcamp.com/stream_redirect?enc=mp3-128&track_id=2768846093&...

#EXTINF:466,Sharon Stoned - Down (SML Club Version feat. Senpolya)
https://bandcamp.com/stream_redirect?enc=mp3-128&track_id=4131226714&...
```

### Text

Human-readable numbered list with durations:

```
  1. Stones Taro - Odoriko feat. MFS [4:49]
  2. Sharon Stoned - Down (SML Club Version feat. Senpolya) [7:46]
  3. Luca Lozano - Delta Force [5:01]
```

### JSON

Array of track objects with full metadata:

```json
[
  {
    "title": "Odoriko feat. MFS",
    "artist": "Stones Taro",
    "duration": 289.88,
    "track_id": 2768846093,
    "stream_url": "https://bandcamp.com/stream_redirect?...",
    "section": "collection"
  }
]
```

## Limitations

- **Stream quality**: Bandcamp only exposes mp3-128 (128 kbps) streams publicly. Higher quality formats (MP3 320, FLAC, WAV) are only available as downloads after purchase.
- **Token expiration**: Stream URLs contain temporary tokens that expire after a few hours. Regenerate the playlist when needed.
- **Public collections only**: The tool can only access public user profiles. Private collections are not accessible.
- **Rate limiting**: When fetching large collections (1000+ items), Bandcamp may throttle requests. The tool handles this gracefully but may take a minute for very large collections.

## How It Works

1. Fetches the user's profile page at `https://bandcamp.com/<username>`
2. Extracts the embedded JSON data blob from the page's `#pagedata` element
3. If `--all-pages` is specified, paginates through Bandcamp's collection API to fetch all items
4. Extracts track metadata and stream URLs from the tracklist data
5. Outputs in the requested format

## Disclaimer

This tool is provided for personal and educational purposes only.

- It only accesses publicly available data from Bandcamp user profiles
- Stream URLs are the same 128kbps previews that Bandcamp serves in its web player
- No DRM or access controls are bypassed
- No copyrighted content is downloaded or redistributed by this tool
- This project is not affiliated with or endorsed by Bandcamp

Users are responsible for ensuring their use complies with Bandcamp's
[Terms of Use](https://bandcamp.com/terms_of_use) and applicable copyright laws.
Stream URLs are temporary and intended for personal listening only.

## License

MIT
