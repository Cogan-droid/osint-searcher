# OSINT Searcher

A high-performance OSINT tool designed to scan massive collections (10,000+ files) of bookmarks and saved web pages locally.

## Features
- **High Speed**: Optimized with a fast pre-filtering pass and multi-threading.
- **Two-Tier Ranking**: Prioritizes matches in Metadata (Title, URL, Description) over the document body.
- **OSINT Focused**: Extracts source URLs (Canonical, OG:URL) from saved HTML pages.
- **Support**: Works with HTML bookmarks, saved web pages, and raw text files.

## How to Use (Windows)
1.  Download this repository.
2.  Run `search.bat`.
3.  Enter your search keyword when prompted.

## Requirements
- Python 3.x
- No external libraries required (uses standard library only).

---
*Developed for rapid discovery in extensive local OSINT data collections.*
