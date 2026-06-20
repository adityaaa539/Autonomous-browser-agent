import os
import threading
import http.server
import socket
import pytest

PORT = 8899
DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))

class DualStackServer(http.server.ThreadingHTTPServer):
    def server_bind(self):
        # Allow instant re-binding of the port (avoids address already in use error on re-runs)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

@pytest.fixture(scope="session", autouse=True)
def http_server():
    server = DualStackServer(("", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()

@pytest.fixture(scope="session")
def local_server(http_server):
    return http_server



import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_engine():
    yield
    from db.database import engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db():
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session
