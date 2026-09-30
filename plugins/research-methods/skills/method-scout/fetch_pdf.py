#!/usr/bin/env python3
"""Download a PDF/page that plain curl gets blocked on (403, bot checks).

Usage: fetch_pdf.py <url> <output-file>     exit 0 = success, 1 = failure

Tries curl first; if that fails, opens the site's origin in a headless Chromium via Playwright to
establish a session, then downloads the URL with that session.
If the output name ends in .pdf, the content must start with %PDF to count as success —
verification pages are often served as HTTP 200 HTML, and checking only the status code would file
them as PDFs. On failure no output file is left behind.

Requirements: curl. For the browser fallback: `pip install playwright` and either
`playwright install chromium` or a system Chrome/Chromium on PATH. Without them the script still
works as a curl downloader with the content check.
"""
import os
import shutil
import subprocess
import sys

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def content_ok(out, expect_pdf):
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        return False
    if not expect_pdf:
        return True
    with open(out, "rb") as f:
        return f.read(5) == b"%PDF-"


def via_curl(url, out, expect_pdf):
    if not shutil.which("curl"):
        print("curl not found, skipping to browser", file=sys.stderr)
        return False
    r = subprocess.run(["curl", "-sL", "-m", "60", "-A", UA, "-o", out, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    if r.stdout.strip() != "200":
        return False
    if not content_ok(out, expect_pdf):
        print("curl got HTTP 200 but the content is not a PDF (probably a verification page); trying browser",
              file=sys.stderr)
        return False
    return True


def via_browser(url, out, expect_pdf):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; no browser fallback", file=sys.stderr)
        return False
    chrome = next((p for p in (shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser")) if p), None)
    origin = "/".join(url.split("/")[:3]) + "/"
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
        except Exception as e:
            print(f"could not start a browser: {e}", file=sys.stderr)
            return False
        try:
            ctx = b.new_context(user_agent=UA)
            ctx.new_page().goto(origin, timeout=45000, wait_until="domcontentloaded")
            r = ctx.request.get(url, timeout=60000)
            if r.status != 200:
                print(f"browser download HTTP {r.status}", file=sys.stderr)
                return False
            with open(out, "wb") as f:
                f.write(r.body())
        except Exception as e:
            print(f"browser download failed: {e}", file=sys.stderr)
            return False
        finally:
            b.close()
    if not content_ok(out, expect_pdf):
        print("the browser also got something that is not a PDF (verification not passed)", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    url, out = sys.argv[1:]
    expect_pdf = out.lower().endswith(".pdf")
    ok = via_curl(url, out, expect_pdf) or via_browser(url, out, expect_pdf)
    if ok:
        if shutil.which("file"):
            print(subprocess.run(["file", out], capture_output=True, text=True).stdout.strip())
        else:
            print(f"saved {out} ({os.path.getsize(out)} bytes)")
    else:
        if os.path.exists(out):
            os.remove(out)
        print(f"failed; no output kept at {out}. Mark this source [unread]", file=sys.stderr)
    sys.exit(0 if ok else 1)
