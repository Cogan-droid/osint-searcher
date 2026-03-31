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
MAX_FILE_BYTES = 250 * 1024  # Increased for better content matching
FILE_EXTENSIONS = ('.html', '.htm', '.txt')

# --- Heuristics for Classification ---
TOOL_DOMAINS = {'github.com', 'gitlab.com', 'pypi.org', 'npmjs.com', 'docker.com', 'replit.com', 'huggingface.co'}
TOOL_KEYWORDS = {'repository', 'tool', 'script', 'library', 'api', 'cli', 'framework', 'standalone', 'software', 'app', 'utility'}
ARTICLE_KEYWORDS = {'article', 'guide', 'tutorial', 'how to', 'review', 'news', 'blog', 'writeup', 'training', 'bellingcat', 'substack', 'medium'}

# --- Synonym Expansion ---
SYNONYM_MAP = {
    'geolocating': ['geolocation', 'map', 'coordinate', 'latitude', 'longitude', 'osm', 'satellite', 'imagery', 'streetview', 'landmark'],
    'social media': ['socmint', 'username', 'profile', 'twitter', 'facebook', 'instagram', 'tiktok', 'linkedin', 'snapchat'],
    'email': ['breach', 'leak', 'mailbox', 'verify', 'osint'],
    'phone': ['hlr', 'caller', 'telephony', 'sms', 'number'],
    'dark web': ['tor', 'onion', 'i2p', 'freenet', 'hidden', 'deepweb'],
}

class Style:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
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

def classify_content(title, url, desc):
    """Heuristic logic to separate tools from articles."""
    text = f"{title} {url} {desc}".lower()
    
    parsed_url = urlparse(url)
    if any(domain in parsed_url.netloc.lower() for domain in TOOL_DOMAINS):
        return "TOOL"
        
    is_tool = any(kw in text for kw in TOOL_KEYWORDS)
    is_article = any(kw in text for kw in ARTICLE_KEYWORDS)
    
    if is_tool and not is_article:
        return "TOOL"
    if is_article:
        return "ARTICLE"
        
    if url != 'N/A' and ('github' in url or 'app' in url or 'tool' in url):
        return "TOOL"
        
    return "UNKNOWN"

def get_synonyms(query):
    query_norm = query.lower().strip()
    return SYNONYM_MAP.get(query_norm, [])

def process_file(fpath, query, synonyms):
    fname = os.path.basename(fpath)
    results = []
    q_all = [query.lower()] + [s.lower() for s in synonyms]
    
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(MAX_FILE_BYTES)
        
        h_lower = head.lower()
        if not any(q in h_lower for q in q_all) and not any(q in fname.lower() for q in q_all):
            return results

        matches_primary = query.lower() in h_lower or query.lower() in fname.lower()
        matches_synonyms = any(s.lower() in h_lower or s.lower() in fname.lower() for s in synonyms)

        if fpath.lower().endswith('.txt'):
            found_q = next((q for q in q_all if q in h_lower), query)
            idx = h_lower.find(found_q)
            start = max(0, idx - 60)
            end = min(len(head), idx + len(found_q) + 60)
            snippet = head[start:end].replace('\n', ' ')
            
            results.append({
                'relevance': 1 if matches_primary else 2,
                'type': 'txt',
                'category': classify_content(fname, 'N/A', head[:100]),
                'file': fname,
                'path': fpath,
                'title': fname,
                'url': 'N/A',
                'snippet': f"... {snippet} ..."
            })
        elif 'NETSCAPE-BOOKMARK' in head.upper() or ('<DL>' in head and '<DT>' in head):
            bp = BookmarksParser()
            bp.feed(head)
            for title, url in bp.bookmarks:
                t_lower, u_lower = title.lower(), url.lower()
                if any(q in t_lower or q in u_lower for q in q_all):
                    rel = 1 if (query.lower() in t_lower or query.lower() in u_lower) else 2
                    results.append({
                        'relevance': rel,
                        'type': 'bookmark',
                        'category': classify_content(title, url, ""),
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
            
            t_low, u_low, d_low = title.lower(), (src_url or "").lower(), desc.lower()
            
            if any(q in t_low or q in u_low or q in d_low or q in h_lower for q in q_all):
                if (query.lower() in t_low or query.lower() in u_low): rel = 1
                elif any(s.lower() in t_low or s.lower() in u_low for s in synonyms): rel = 2
                else: rel = 3
                
                results.append({
                    'relevance': rel,
                    'type': 'html',
                    'category': classify_content(title, src_url or 'N/A', desc),
                    'file': fname,
                    'path': fpath,
                    'title': title,
                    'url': src_url or 'N/A',
                    'snippet': desc[:140] + "..." if desc else "Content match in document body"
                })
    except Exception:
        pass
        
    return results

def main():
    parser = argparse.ArgumentParser(description="Advanced OSINT Search & Discovery Tool")
    parser.add_argument("query", help="Keyword to search for")
    parser.add_argument("--tools-only", action="store_true", help="Filter for software/repos only")
    args = parser.parse_args()
    
    query = args.query
    synonyms = get_synonyms(query)
    
    print(f"\n{Style.CYAN}{Style.BOLD}🔍 OSINT Smart Searcher{Style.RESET}")
    print(f"{Style.DIM}Query:    {Style.YELLOW}'{query}'{Style.RESET}")
    if synonyms:
        print(f"{Style.DIM}Synonyms: {Style.CYAN}{', '.join(synonyms)}{Style.RESET}")
    if args.tools_only:
        print(f"{Style.MAGENTA}{Style.BOLD}[TOOLS ONLY MODE ACTIVE]{Style.RESET}")
    print(f"{Style.DIM}{'-'*60}{Style.RESET}\n")

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

    all_matches = []
    processed_count = 0
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_file, f, query, synonyms): f for f in files_to_scan}
        for future in concurrent.futures.as_completed(futures):
            processed_count += 1
            if processed_count % 500 == 0:
                print(f"{Style.BLUE}Scanning {len(files_to_scan):,} files... ({processed_count:,} processed){Style.RESET}", end="\r")
            all_matches.extend(future.result())

    if args.tools_only:
        all_matches = [m for m in all_matches if m['category'] == 'TOOL']

    print(f"{Style.BLUE}Scanning complete! Found {len(all_matches):,} results in {len(files_to_scan):,} files.{Style.RESET}    \n")

    if not all_matches:
        print(f"{Style.RED}❌ No matches found for '{query}'.{Style.RESET}\n")
        return

    cat_order = {'TOOL': 0, 'ARTICLE': 1, 'UNKNOWN': 2}
    all_matches.sort(key=lambda x: (cat_order.get(x['category'], 3), x['relevance'], x['title']))

    last_cat = None
    for m in all_matches:
        if m['category'] != last_cat:
            cat_label = f"--- {m['category']}S ---"
            color = Style.GREEN if m['category'] == 'TOOL' else Style.MAGENTA
            print(f"\n{Style.BOLD}{color}{cat_label}{Style.RESET}")
            last_cat = m['category']

        rel_color = Style.BLUE if m['relevance'] == 1 else Style.DIM
        print(f"\n{Style.BOLD}[{m['type'].upper()}]{Style.RESET} {Style.BOLD}{m['title']}{Style.RESET}")
        print(f"   {Style.BOLD}URL:{Style.RESET}   {m['url']}")
        print(f"   {Style.BOLD}File:{Style.RESET}  {Style.DIM}{m['path']}{Style.RESET}")
        if m['snippet'] != 'N/A' and m['snippet']:
            print(f"   {Style.BOLD}Match:{Style.RESET} {rel_color}{m['snippet']}{Style.RESET}")

    print(f"\n{Style.CYAN}{'='*70}{Style.RESET}")
    print(f"✅ Search complete. {len(all_matches)} results displayed.")
    print(f"{Style.CYAN}{'='*70}{Style.RESET}\n")

if __name__ == "__main__":
    main()
