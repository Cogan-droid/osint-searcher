import os
import re
import sys
import argparse
import concurrent.futures
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime

# --- Configuration ---
DOWNLOADS_DIR = r"C:\Users\v-conmounsey\Downloads"
ONEDRIVE_DIR = r"C:\Users\v-conmounsey\OneDrive - Microsoft\Documents\OneDrive_1_2-24-2026"
MAX_FILE_BYTES = 200 * 1024  # Increased to 200KB for better full-text coverage
FILE_EXTENSIONS = ('.html', '.htm', '.txt')

class Style:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DIM = '\033[2m'
    RESET = '\033[0m'

# --- Parsers ---

class BookmarksParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self._in_a = False
        self._text = []
        self._href = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self._in_a = True
            self._text = []
            for n, v in attrs:
                if n.lower() == 'href':
                    self._href = v

    def handle_data(self, data):
        if self._in_a:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a':
            title = "".join(self._text).strip()
            self.bookmarks.append((title, self._href))
            self._in_a = False

class SavedPageExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical_url = ''
        self.og_url = ''
        self.title = ''
        self.meta_desc = ''
        self._in_title = False
        self._title_text = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        attr_dict = {n.lower(): v for n, v in attrs}
        
        if t == 'link' and attr_dict.get('rel') == 'canonical':
            self.canonical_url = attr_dict.get('href', '')
        elif t == 'meta':
            prop = attr_dict.get('property', '')
            name = attr_dict.get('name', '')
            content = attr_dict.get('content', '')
            if prop == 'og:url':
                self.og_url = content
            elif name == 'description' or prop == 'og:description':
                self.meta_desc = content
        elif t == 'title':
            self._in_title = True
            self._title_text = []

    def handle_data(self, data):
        if self._in_title:
            self._title_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.title = "".join(self._title_text).strip()
            self._in_title = False

    def handle_comment(self, data):
        m = re.search(r'saved from url=\((\d+)\)(https?://\S+)', data)
        if m and not self.canonical_url:
            self.canonical_url = m.group(2)

# --- Logic ---

def is_bookmark_file(content_head):
    return 'NETSCAPE-BOOKMARK' in content_head.upper() or ('<DL>' in content_head and '<DT>' in content_head)

def process_file(fpath, query):
    fname = os.path.basename(fpath)
    results = []
    q_lower = query.lower()
    
    try:
        # 1. Fast binary/text check (The Optimization)
        # We read the head first as a raw string to see if the query exists at ALL.
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(MAX_FILE_BYTES)
        
        if q_lower not in head.lower() and q_lower not in fname.lower():
            return results # Early exit

        # 2. Metadata Priority Check
        if fpath.lower().endswith('.txt'):
            idx = head.lower().find(q_lower)
            start = max(0, idx - 40)
            end = min(len(head), idx + len(query) + 40)
            snippet = head[start:end].replace('\n', ' ')
            results.append({
                'relevance': 2, # Content match
                'type': 'txt',
                'file': fname,
                'path': fpath,
                'title': fname,
                'url': 'N/A',
                'snippet': f"... {snippet} ..."
            })
        elif is_bookmark_file(head):
            bp = BookmarksParser()
            bp.feed(head)
            for title, url in bp.bookmarks:
                if q_lower in title.lower() or q_lower in url.lower():
                    results.append({
                        'relevance': 1, # Metadata match (High)
                        'type': 'bookmark',
                        'file': fname,
                        'path': fpath,
                        'title': title,
                        'url': url,
                        'snippet': 'N/A'
                    })
        else:
            spe = SavedPageExtractor()
            spe.feed(head)
            src_url = spe.canonical_url or spe.og_url
            title = spe.title or fname
            desc = spe.meta_desc or ""
            
            # Check Title/URL/Desc first (High Relevance)
            if (q_lower in title.lower() or 
                q_lower in (src_url or "").lower() or 
                q_lower in desc.lower()):
                relevance = 1
            else:
                relevance = 2 # Content-only match (Medium)
            
            results.append({
                'relevance': relevance,
                'type': 'html',
                'file': fname,
                'path': fpath,
                'title': title,
                'url': src_url or 'N/A',
                'snippet': desc[:120] + "..." if desc else "Content match in body"
            })
    except Exception:
        pass
        
    return results

def main():
    parser = argparse.ArgumentParser(description="OSINT Bookmark & Saved Page Searcher")
    parser.add_argument("query", help="Keyword to search for")
    args = parser.parse_args()
    
    query = args.query
    print(f"\n{Style.CYAN}{Style.BOLD}🔍 OSINT Searcher (Optimized){Style.RESET}")
    print(f"{Style.DIM}Query: '{query}'{Style.RESET}\n")

    # Gather files
    files_to_scan = []
    scan_dirs = [DOWNLOADS_DIR]
    if os.path.exists(ONEDRIVE_DIR):
        scan_dirs.append(ONEDRIVE_DIR)

    for d in scan_dirs:
        for root, _, files in os.walk(d):
            if any(x in root.lower() for x in ["_files", "node_modules", ".git"]): continue
            for f in files:
                if f.lower().endswith(FILE_EXTENSIONS):
                    files_to_scan.append(os.path.join(root, f))

    print(f"{Style.BLUE}Scanning {len(files_to_scan):,} files...{Style.RESET}", end="\r")

    all_matches = []
    processed_count = 0
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_file, f, query): f for f in files_to_scan}
        for future in concurrent.futures.as_completed(futures):
            processed_count += 1
            if processed_count % 500 == 0:
                print(f"{Style.BLUE}Scanning {len(files_to_scan):,} files... ({processed_count:,} processed){Style.RESET}", end="\r")
            
            all_matches.extend(future.result())

    print(f"{Style.BLUE}Scanning complete! Found {len(all_matches):,} matches in {len(files_to_scan):,} files.{Style.RESET}    \n")

    if not all_matches:
        print(f"{Style.RED}❌ No matches found for '{query}'.{Style.RESET}\n")
        return

    # Sort matches: Relevance (1=Meta, 2=Content) then Title
    all_matches.sort(key=lambda x: (x['relevance'], x['title']))

    last_rel = None
    for m in all_matches:
        if m['relevance'] != last_rel:
            rel_label = "HIGH RELEVANCE (Metadata Match)" if m['relevance'] == 1 else "MEDIUM RELEVANCE (Content Match)"
            print(f"\n{Style.BOLD}{Style.UNDERLINE}{rel_label}{Style.RESET}")
            last_rel = m['relevance']

        color = Style.GREEN if m['type'] == 'bookmark' else Style.YELLOW
        print(f"\n{Style.BOLD}[{m['type'].upper()}]{Style.RESET} {color}{m['title']}{Style.RESET}")
        print(f"   {Style.BOLD}URL:{Style.RESET}   {m['url']}")
        print(f"   {Style.BOLD}File:{Style.RESET}  {m['path']}")
        if m['snippet'] != 'N/A' and m['snippet']:
            print(f"   {Style.BOLD}Match:{Style.RESET} {Style.DIM}{m['snippet']}{Style.RESET}")

    print(f"\n{Style.CYAN}{'='*70}{Style.RESET}")
    print(f"✅ Search complete.")
    print(f"{Style.CYAN}{'='*70}{Style.RESET}\n")

if __name__ == "__main__":
    main()
