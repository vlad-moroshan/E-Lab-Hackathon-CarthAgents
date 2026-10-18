"""Local hackathon upload bridge. Run: python -m carth.server --specs out/layouts."""
from __future__ import annotations
import argparse
import base64
import json
import tempfile
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from carth import ingest
from carth.output import extract, write_outputs

MAX_UPLOAD = 50 * 1024 * 1024


def process_file(source: Path, specs: Path | None, out: Path) -> dict:
    doc = ingest.ingest(source)
    spec_path = specs / f'{source.stem}.layout.json' if specs else None
    spec = json.loads(spec_path.read_text()) if spec_path and spec_path.is_file() else None
    result = extract(doc, spec, source.stem)
    if not result['values']:
        raise ValueError('This document needs a reviewed layout before values can be extracted. ' + '; '.join(result['flags']))
    jp, wp = write_outputs(result, out)
    return {'result': json.loads(jp.read_text()),
            'workbook': {'name': f'{source.stem}-Arbeitsversion.xlsx', 'base64': base64.b64encode(wp.read_bytes()).decode()}}


def handler(specs: Path | None, origins: set[str]):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            origin = self.headers.get('Origin')
            if origin in origins:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self.reply(200 if self.path == '/api/health' else 404,
                       {'status': 'ready', 'layout_required': True} if self.path == '/api/health' else {'error': 'Not found'})

        def do_POST(self):
            if self.path != '/api/process':
                return self.reply(404, {'error': 'Not found'})
            if self.headers.get('Origin') and self.headers['Origin'] not in origins:
                return self.reply(403, {'error': 'Frontend origin is not allowed'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_UPLOAD + 65536:
                    return self.reply(413, {'error': 'Choose a source document smaller than 50 MB.'})
                content_type = self.headers.get('Content-Type', '')
                if not content_type.lower().startswith('multipart/form-data;'):
                    raise ValueError('Expected multipart/form-data with one file field')
                message = BytesParser(policy=policy.default).parsebytes(
                    f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode() + self.rfile.read(length))
                parts = list(message.iter_parts())
                if len(parts) != 1 or parts[0].get_param('name', header='content-disposition') != 'file':
                    raise ValueError('Upload exactly one source document in the file field')
                name = Path((parts[0].get_filename() or '').replace('\\', '/')).name
                data = parts[0].get_payload(decode=True)
                if Path(name).suffix.lower() not in ('.pdf', '.xlsx') or not data or len(data) > MAX_UPLOAD:
                    raise ValueError('Choose a nonempty PDF or XLSX smaller than 50 MB')
                with tempfile.TemporaryDirectory(prefix='carth-upload-') as tmp:
                    root = Path(tmp)
                    source = root / name
                    source.write_bytes(data)
                    response = process_file(source, specs, root / 'results')
                self.reply(200, response)
            except (ValueError, json.JSONDecodeError) as exc:
                self.reply(422, {'error': str(exc)})
            except Exception as exc:
                self.log_error('Processing failed: %s', exc)
                self.reply(500, {'error': 'Processing failed. Check the backend terminal for details.'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--specs', type=Path, default=Path('out/layouts'))
    parser.add_argument('--origin', action='append', default=['http://127.0.0.1:5173', 'http://localhost:5173'])
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.specs, set(args.origin)))
    print(f'Local upload bridge: http://127.0.0.1:{args.port}; layouts: {args.specs}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
