#!/usr/bin/env python3
"""Serve a remote PMTiles archive through small parallel upstream ranges."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def parse_range(value: str | None, size: int) -> tuple[int, int]:
    if not value or not value.startswith("bytes=") or "," in value:
        raise ValueError("one explicit byte range is required")
    start_text, separator, end_text = value[6:].partition("-")
    if not separator or not start_text:
        raise ValueError("suffix and malformed ranges are unsupported")
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or end < start or end >= size:
        raise ValueError("range is outside the source")
    return start, end


def split_range(start: int, end: int, chunk_size: int) -> list[tuple[int, int]]:
    if chunk_size < 1:
        raise ValueError("chunk size must be positive")
    return [(offset, min(offset + chunk_size - 1, end)) for offset in range(start, end + 1, chunk_size)]


class Upstream:
    def __init__(self, source: str, chunk_size: int, workers: int, retries: int) -> None:
        parsed = urlsplit(source)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("source must be an HTTPS URL")
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.chunk_size = chunk_size
        self.retries = retries
        self.context = ssl.create_default_context()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self.metrics_lock = threading.Lock()
        self.requests = 0
        self.bytes = 0
        self.size, self.etag = self._head()

    def _connection(self) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(self.host, self.port, timeout=20, context=self.context)

    def _head(self) -> tuple[int, str | None]:
        connection = self._connection()
        try:
            connection.request("HEAD", self.path, headers={"User-Agent": "anav-map-packs/1"})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"upstream HEAD returned HTTP {response.status}")
            size = int(response.getheader("Content-Length", "0"))
            if size < 1:
                raise RuntimeError("upstream HEAD has no valid Content-Length")
            return size, response.getheader("ETag")
        finally:
            connection.close()

    def _fetch_chunk(self, item: tuple[int, int]) -> bytes:
        start, end = item
        expected = end - start + 1
        error: Exception | None = None
        for _ in range(self.retries):
            connection = self._connection()
            try:
                connection.request(
                    "GET",
                    self.path,
                    headers={
                        "Range": f"bytes={start}-{end}",
                        "User-Agent": "anav-map-packs/1",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                body = response.read()
                if response.status != 206 or len(body) != expected:
                    raise RuntimeError(
                        f"range {start}-{end}: HTTP {response.status}, expected {expected}, got {len(body)}"
                    )
                with self.metrics_lock:
                    self.requests += 1
                    self.bytes += len(body)
                return body
            except Exception as caught:
                error = caught
            finally:
                connection.close()
        raise RuntimeError(f"range {start}-{end} failed after {self.retries} attempts: {error}")

    def fetch(self, start: int, end: int) -> bytes:
        return b"".join(self.pool.map(self._fetch_chunk, split_range(start, end, self.chunk_size)))


def handler_for(upstream: Upstream) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(upstream.size))
            if upstream.etag:
                self.send_header("ETag", upstream.etag)
            self.end_headers()

        def do_GET(self) -> None:
            try:
                start, end = parse_range(self.headers.get("Range"), upstream.size)
                body = upstream.fetch(start, end)
            except ValueError as error:
                self.send_error(416, str(error))
                return
            except Exception as error:
                self.send_error(502, str(error))
                return
            self.send_response(206)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{upstream.size}")
            self.send_header("Content-Length", str(len(body)))
            if upstream.etag:
                self.send_header("ETag", upstream.etag)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            print(f"client={self.client_address[0]} {format % args}", flush=True)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--chunk-size", type=int, default=4096)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    upstream = Upstream(args.source, args.chunk_size, args.workers, args.retries)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(upstream))
    print(
        f"ready source_bytes={upstream.size} chunk_size={args.chunk_size} workers={args.workers}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        print(f"upstream_requests={upstream.requests} upstream_bytes={upstream.bytes}", flush=True)
        upstream.pool.shutdown(wait=False, cancel_futures=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
