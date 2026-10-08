"""Download one public paper PDF into a project's inbox."""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import re
from pathlib import Path
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

MAX_BYTES = 49_000_000
USER_AGENT = "paper-report/1.0 (personal research workflow)"
ARXIV_ID = re.compile(r"(?:arxiv:)?(?P<id>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)", re.I)


def normalize_title(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def arxiv_id(value: str) -> str | None:
    match = ARXIV_ID.search(urllib.parse.unquote(value))
    return match.group("id") if match else None


def query_arxiv(search_query: str, max_results: int, sort_by: str = "relevance") -> list[dict]:
    query = urllib.parse.urlencode({
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    })
    req = urllib.request.Request(f"https://export.arxiv.org/api/query?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            root = ET.fromstring(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("arXiv search is rate-limited (HTTP 429). Do not retry immediately") from None
        raise RuntimeError(f"arXiv search failed (HTTP {exc.code})") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"arXiv search network error: {exc.reason}") from None
    except TimeoutError:
        raise RuntimeError("arXiv search timed out. Use an academic search tool or try again later") from None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("a:entry", ns):
        found_id = arxiv_id(entry.findtext("a:id", "", ns))
        if found_id:
            results.append({
                "id": found_id,
                "title": " ".join(entry.findtext("a:title", "", ns).split()),
                "published": entry.findtext("a:published", "", ns),
                "authors": [author.findtext("a:name", "", ns) for author in entry.findall("a:author", ns)],
            })
    return results


def search_title(title: str) -> tuple[str, str]:
    results = query_arxiv(f'ti:"{title}"', 5)
    candidates = []
    wanted = normalize_title(title)
    for result in results:
        score = SequenceMatcher(None, wanted, normalize_title(result["title"])).ratio()
        candidates.append((score, result["id"], result["title"]))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0] < 0.88 or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.08):
        lines = ["Title search is ambiguous. Use an arXiv ID or URL. Candidates:"]
        lines.extend(f"- {item[1]}: {item[2]}" for item in candidates)
        raise RuntimeError("\n".join(lines))
    return candidates[0][1], candidates[0][2]


def topic_query(topic: str) -> str:
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    terms = [term for term in re.findall(r"[A-Za-z0-9_.+-]+", topic) if term.lower() not in stopwords]
    if not terms:
        raise RuntimeError("Topic must contain at least one searchable term")
    return " AND ".join(f'all:"{term}"' for term in terms)


def search_topic(topic: str, max_results: int) -> list[dict]:
    return query_arxiv(topic_query(topic), max_results, "relevance")


def safe_filename(url: str, content_disposition: str | None) -> str:
    name = ""
    if content_disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition, re.I)
        if match:
            name = urllib.parse.unquote(match.group(1).strip())
    if not name:
        name = Path(urllib.parse.urlparse(url).path).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "paper.pdf"
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def download(url: str, inbox: Path, preferred_name: str | None = None) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Only public HTTPS PDF URLs are accepted")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            content_type = response.headers.get_content_type().lower()
            final_url = response.geturl()
            name = preferred_name or safe_filename(final_url, response.headers.get("Content-Disposition"))
            chunks, total = [], 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise RuntimeError("PDF exceeds the 49 MB workflow limit")
                chunks.append(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Paper download failed (HTTP {exc.code})") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Paper download network error: {exc.reason}") from None
    except TimeoutError:
        raise RuntimeError("Paper download timed out") from None
    data = b"".join(chunks)
    if content_type != "application/pdf" and not data.startswith(b"%PDF-"):
        raise RuntimeError(f"URL did not return a PDF (content type: {content_type})")
    if not data.startswith(b"%PDF-"):
        raise RuntimeError("Downloaded file does not have a PDF header")
    inbox.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).digest()
    for existing in inbox.glob("*.pdf"):
        if existing.is_file() and existing.stat().st_size == len(data):
            if hashlib.sha256(existing.read_bytes()).digest() == digest:
                print(f"UNCHANGED\t{existing}")
                return existing
    target = inbox / name
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite a different file: {target}")
    temp = target.with_suffix(target.suffix + ".part")
    temp.write_bytes(data)
    temp.replace(target)
    print(f"DOWNLOADED\t{target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Search for and download public paper PDFs to inbox")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--arxiv", help="arXiv ID, such as 2608.06791v1")
    source.add_argument("--url", help="Public HTTPS PDF or arXiv URL")
    source.add_argument("--title", help="Exact paper title to search on arXiv")
    source.add_argument("--topic", help="Topic terms to search in arXiv titles and abstracts")
    parser.add_argument("--max-results", type=int, default=5, help="Topic results to download (1-10, default: 5)")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if not 1 <= args.max_results <= 10:
        parser.error("--max-results must be between 1 and 10")
    if args.topic:
        results = search_topic(args.topic, args.max_results)
        if not results:
            raise RuntimeError("No arXiv papers matched the topic")
        print(f"FOUND\t{len(results)}\t{args.topic}")
        inbox = args.project.resolve() / "inbox"
        for result in results:
            print(f"RESULT\t{result['id']}\t{result['published'][:10]}\t{result['title']}")
            time.sleep(3)
            preferred = re.sub(r"/", "_", result["id"]) + ".pdf"
            download(f"https://arxiv.org/pdf/{result['id']}", inbox, preferred)
        return 0

    paper_id, resolved_title = None, None
    if args.title:
        paper_id, resolved_title = search_title(args.title)
    elif args.arxiv:
        paper_id = arxiv_id(args.arxiv)
        if not paper_id:
            raise RuntimeError("Invalid arXiv ID")
    elif args.url:
        paper_id = arxiv_id(args.url) if "arxiv.org" in urllib.parse.urlparse(args.url).netloc.lower() else None

    if paper_id:
        url = f"https://arxiv.org/pdf/{paper_id}"
        versioned = paper_id if re.search(r"v\d+$", paper_id, re.I) else paper_id
        preferred = re.sub(r"/", "_", versioned) + ".pdf"
    else:
        url, preferred = args.url, None
    if resolved_title:
        print(f"MATCHED\t{paper_id}\t{resolved_title}")
        time.sleep(3)
    download(url, args.project.resolve() / "inbox", preferred)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
