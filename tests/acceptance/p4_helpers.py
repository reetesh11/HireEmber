"""Shared helpers for the phase-4 web dashboard acceptance tests (public surfaces only)."""

import http.client
import json
import threading
import time

from p1_helpers import add_job  # noqa: F401  (re-exported)

STATUSES = ("pending", "started", "applying", "blocked for human", "applied", "skipped", "closed")


def make_ticket(conn, name, status="pending", *, company="Acme", title=None, location="Berlin",
                score=8, **columns) -> int:
    """Create a job + ticket, force its status and extra ticket columns; return the ticket id."""
    url = f"https://jobs.example/{name}"
    tid = add_job(conn, url, title=title or f"Engineer {name}", location=location,
                  company=company, score=score)
    columns = dict(columns, status=status)
    sets = ", ".join(f"{k} = ?" for k in columns)
    conn.execute(f"UPDATE tickets SET {sets} WHERE id = ?", (*columns.values(), tid))
    conn.commit()
    return tid


def start_server(db_path):
    from hireember.web.server import create_server

    server = create_server("127.0.0.1", 0, db_path=db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class Client:
    def __init__(self, port):
        self.port = port

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        hdrs = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        try:
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            payload = resp.read()
            return resp.status, dict(resp.getheaders()), payload
        finally:
            conn.close()

    def json(self, method, path, body=None, headers=None):
        status, hdrs, payload = self.request(method, path, body, headers)
        return status, json.loads(payload.decode("utf-8")) if payload else None

    def get(self, path):
        return self.json("GET", path)

    def timed_get(self, path):
        start = time.perf_counter()
        status, _ = self.get(path)
        return status, time.perf_counter() - start


def seed_many(conn, n=5000):
    from hireember.database import store_jobs

    jobs = [{"url": f"https://bulk.example/{i}", "title": f"Role {i}", "location": f"City {i % 50}",
             "company": f"Company {i % 200}"} for i in range(n)]
    store_jobs(conn, jobs, "Bulk", "test")
    statuses = list(STATUSES)
    conn.executemany(
        "INSERT INTO tickets (job_url, status, status_reason, score, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?, ?)",
        [(f"https://bulk.example/{i}", statuses[i % 7], i % 101,
          f"2026-02-{1 + i % 27:02d}T10:00:00", f"2026-03-{1 + i % 27:02d}T10:00:00")
         for i in range(n)])
    conn.commit()
