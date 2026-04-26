from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import json
import psycopg2
from psycopg2 import pool
import os
import re
from dotenv import load_dotenv

load_dotenv()

# ---------- DB CONFIG ----------
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "waitlist"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
}

# ---------- CONNECTION POOL ----------
db_pool = psycopg2.pool.SimpleConnectionPool(
    1, 10, **DB_CONFIG
)

# ---------- DB INIT ----------
def init_db():
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE
        )
        """)
        conn.commit()
        cur.close()
    finally:
        db_pool.putconn(conn)

init_db()


# ---------- EMAIL VALIDATION ----------
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# ---------- THREADED SERVER ----------
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


# ---------- HANDLER ----------
class Handler(BaseHTTPRequestHandler):

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_POST(self):
        if self.path != "/waitlist":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            email = data.get("email", "").strip()

            if not email:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Email required"}).encode())
                return

            if not is_valid_email(email):
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Invalid email format"}).encode())
                return

            conn = db_pool.getconn()
            try:
                cur = conn.cursor()

                cur.execute(
                    "INSERT INTO waitlist (email) VALUES (%s)",
                    (email,)
                )

                conn.commit()
                cur.close()

                self._set_headers(200)
                self.wfile.write(json.dumps({"message": "Added to waitlist"}).encode())

            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Email already exists"}).encode())

            finally:
                db_pool.putconn(conn)

        except json.JSONDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())

        except Exception:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": "Server error"}).encode())


# ---------- START SERVER ----------
if __name__ == "__main__":
    server = ThreadedHTTPServer(("localhost", 8000), Handler)
    print("Server running on http://localhost:8000")
    server.serve_forever()