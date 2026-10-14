"""Local-only preview server with byte ranges for reliable video seeking."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil

OUT = Path(__file__).resolve().parents[2] / 'outputs/sui-frisbee-3d'


class MediaHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.range_remaining = None
        value = self.headers.get('Range')
        path = Path(self.translate_path(self.path))
        if not value or not path.is_file():
            return super().send_head()
        match = re.fullmatch(r'bytes=(\d*)-(\d*)',value.strip())
        if not match:
            self.send_error(416,'Single byte range required')
            return None
        size = path.stat().st_size
        a,b = match.groups()
        start = int(a) if a else max(0,size-int(b or size))
        end = min(size-1,int(b) if a and b else size-1)
        if start>end or start>=size:
            self.send_response(416)
            self.send_header('Content-Range',f'bytes */{size}')
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length',str(end-start+1))
        self.end_headers()
        file = path.open('rb')
        file.seek(start)
        self.range_remaining = end-start+1
        return file

    def copyfile(self,source,outputfile):
        if self.range_remaining is None:
            return shutil.copyfileobj(source,outputfile)
        remaining = self.range_remaining
        while remaining:
            buf = source.read(min(remaining,128*1024))
            if not buf:
                break
            outputfile.write(buf)
            remaining -= len(buf)


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(MediaHandler,directory=str(OUT)))
    print(f'http://127.0.0.1:{args.port}/watch.html',flush=True)
    server.serve_forever()
