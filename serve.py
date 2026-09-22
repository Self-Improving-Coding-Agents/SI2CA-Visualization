#!/usr/bin/env python3
"""Serve this repository so the page can fetch and gunzip the records in paper_data/.

    python3 serve.py            # http://127.0.0.1:8013/site/
    python3 serve.py 9000       # another port
"""
import http.server, os, re, socketserver, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8013


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


RANGE = re.compile(r'bytes=(\d*)-(\d*)$')


class Slice:
    """A file-like view of `n` bytes from the current position, for copyfile()."""
    def __init__(self, f, n):
        self.f, self.n = f, n

    def read(self, k=-1):
        if self.n <= 0:
            return b''
        b = self.f.read(self.n if k is None or k < 0 else min(k, self.n))
        self.n -= len(b)
        return b

    def close(self):
        self.f.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        # always revalidate, so an edited page is never paired with a cached script
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        # SimpleHTTPRequestHandler ignores Range requests; browsers need them to seek inside a video
        # (and to read the mp4 index before the whole file has arrived), so serve partial content.
        path = self.translate_path(self.path)
        m = RANGE.match((self.headers.get('Range') or '').strip())
        if not m or not os.path.isfile(path) or m.group(1) == m.group(2) == '':
            return super().send_head()
        size = os.path.getsize(path)
        first, last = m.groups()
        if first == '':                                   # bytes=-N: the last N bytes
            start, end = max(size - int(last), 0), size - 1
        else:
            start, end = int(first), (min(int(last), size - 1) if last else size - 1)
        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return None
        f = open(path, 'rb')
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Last-Modified', self.date_time_string(os.fstat(f.fileno()).st_mtime))
        self.end_headers()
        f.seek(start)
        return Slice(f, end - start + 1)

    def guess_type(self, path):
        # hand the browser the compressed bytes; the page gunzips them itself
        return 'application/octet-stream' if str(path).endswith('.gz') else super().guess_type(path)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    with Server(('127.0.0.1', PORT), Handler) as httpd:
        print(f'serving {ROOT}\n  open http://127.0.0.1:{PORT}/site/\nCtrl-C to stop')
        httpd.serve_forever()
