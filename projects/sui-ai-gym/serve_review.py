"""Serve the local review with byte ranges so browser video seeking works."""
from __future__ import annotations

import argparse
import functools
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'outputs/sui-ai-gym-20261012'


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self._range_remaining = None
            return super().send_head()
        try:
            stream = path.open('rb')
        except OSError:
            self.send_error(404)
            return None
        size = path.stat().st_size
        start, end = 0, size - 1
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
            if match and any(match.groups()):
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                else:
                    start = max(0, size - int(last))
            if not match or not any(match.groups()) or start > end or start >= size:
                stream.close()
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return None
        length = max(0, end - start + 1)
        self._range_remaining = length
        self.send_response(206 if requested else 200)
        content_type = self.guess_type(str(path))
        if content_type.startswith('text/'):
            content_type += '; charset=utf-8'
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Last-Modified', self.date_time_string(path.stat().st_mtime))
        if requested:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if path.suffix == '.html':
            self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        stream.seek(start)
        return stream

    def copyfile(self, source, outputfile):
        remaining = getattr(self, '_range_remaining', None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        try:
            while remaining:
                block = source.read(min(512 * 1024, remaining))
                if not block:
                    break
                outputfile.write(block)
                remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Seeking cancels the old transfer.

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8908)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port),
                                 functools.partial(RangeHandler, directory=str(OUT)))
    print(f'Review: http://127.0.0.1:{args.port}/sound-review.html', flush=True)
    server.serve_forever()
