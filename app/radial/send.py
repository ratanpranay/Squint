"""Moving files between this computer and a phone or another computer on
the same Wi-Fi. No cloud, no account, nothing installed on the phone.

* Phone: the computer serves a small page; the phone scans a QR code to
  open it, then downloads what is offered or uploads its own files.
* Another computer running Squint: the receiver opens "Receive"; the
  sender finds it on the network, asks, and sends once it is accepted.

Everything needs a key that is only in the QR code (or handed over after
the receiver said yes), so other machines on the network cannot read or
drop files. Files arrive in Downloads/Squint/Received.
"""
import html
import json
import os
import queue
import secrets
import socket
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import common, qr

PORT = 53317
DISCOVERY_PORT = 53318
HELLO = b"SQUINT-SEND-HELLO-1"
CHUNK = 1 << 20


def lan_ip():
    """The address other devices on this network reach us at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 1))    # sends nothing
        return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


def device_name():
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def _safe_name(name):
    name = os.path.basename(name.replace("\\", "/")).strip() or "file"
    for bad in '<>:"/\\|?*\0':
        name = name.replace(bad, "_")
    return name[:180]


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Squint · %(name)s</title><style>
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#16181d;
color:#e8eaf0;margin:0;padding:20px;max-width:560px;margin:auto}
h1{font-size:20px;margin:4px 0 2px}p{color:#a9afbc;font-size:14px;margin:0 0 18px}
.card{background:#232731;border:1px solid #343944;border-radius:14px;padding:14px;margin-bottom:16px}
h2{font-size:15px;margin:0 0 10px}a.f{display:flex;justify-content:space-between;
padding:12px;border-radius:10px;background:#2c3240;color:#e8eaf0;text-decoration:none;margin-bottom:6px}
a.f span{color:#a9afbc;font-size:13px}label.b{display:block;text-align:center;padding:14px;
border-radius:10px;background:#3d7bf5;color:#fff;font-weight:600}input{display:none}
.row{font-size:13px;color:#a9afbc;margin-top:8px}.ok{color:#5fd38d}
</style></head><body><h1>%(name)s</h1><p>Squint · same Wi-Fi only</p>%(files)s%(upload)s
<script>
const key=%(key)s;
function send(files){const list=document.getElementById('log');
 let i=0;const next=()=>{if(i>=files.length)return;const f=files[i++];
 const row=document.createElement('div');row.className='row';row.textContent=f.name+' …';list.appendChild(row);
 const x=new XMLHttpRequest();x.open('POST','/put?k='+key+'&name='+encodeURIComponent(f.name));
 x.upload.onprogress=e=>{if(e.lengthComputable)row.textContent=f.name+' '+Math.round(100*e.loaded/e.total)+'%%'};
 x.onload=()=>{row.textContent=f.name+(x.status==200?' ✓ sent':' failed');if(x.status==200)row.className='row ok';next()};
 x.onerror=()=>{row.textContent=f.name+' failed';next()};x.send(f)};next()}
</script></body></html>"""


def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0


class Server:
    """One HTTP server per open send/receive window."""

    def __init__(self, shared=(), receive=True, events=None):
        self.key = secrets.token_urlsafe(8)
        self.tickets = set()
        self.shared = list(shared)
        self.receive = receive
        self.events = events or queue.Queue()
        self.ask = None          # set by the receive window: offer -> bool
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a):
                pass

            def _allowed(self, query):
                k = (query.get("k") or [""])[0]
                return secrets.compare_digest(k, server.key) or \
                    k in server.tickets

            def _reply(self, code, body, ctype="text/html; charset=utf-8"):
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(url.query)
                if url.path == "/ping":
                    return self._reply(200, json.dumps(
                        {"app": "squint", "name": device_name()}),
                        "application/json")
                if not self._allowed(query):
                    return self._reply(403, "This link has expired.")
                if url.path == "/":
                    return self._reply(200, server.page())
                if url.path.startswith("/f/"):
                    try:
                        path = server.shared[int(url.path[3:])]
                    except (ValueError, IndexError):
                        return self._reply(404, "Not found")
                    size = os.path.getsize(path)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.send_header(
                        "Content-Disposition", "attachment; filename*=UTF-8''%s"
                        % urllib.parse.quote(os.path.basename(path)))
                    self.end_headers()
                    with open(path, "rb") as fh:
                        while True:
                            chunk = fh.read(CHUNK)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                    server.events.put(("sent", os.path.basename(path)))
                    return None
                return self._reply(404, "Not found")

            def do_POST(self):
                url = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(url.query)
                length = int(self.headers.get("Content-Length") or 0)
                if url.path == "/offer":
                    offer = json.loads(self.rfile.read(min(length, 65536))
                                       or b"{}")
                    if not server.receive or server.ask is None:
                        return self._reply(403, "{}", "application/json")
                    ok = server.ask(offer)
                    if not ok:
                        return self._reply(403, "{}", "application/json")
                    ticket = secrets.token_urlsafe(8)
                    server.tickets.add(ticket)
                    return self._reply(200, json.dumps({"ticket": ticket}),
                                       "application/json")
                if url.path != "/put" or not server.receive or \
                        not self._allowed(query):
                    self.rfile.read(length) if length < CHUNK else None
                    return self._reply(403, "No")
                name = _safe_name((query.get("name") or ["file"])[0])
                target = common.unique(os.path.join(common.received_dir(),
                                                    name))
                got = 0
                server.events.put(("receiving", name, 0, length))
                with open(target + ".part", "wb") as out:
                    while got < length:
                        chunk = self.rfile.read(min(CHUNK, length - got))
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                        server.events.put(("receiving", name, got, length))
                if got != length:
                    os.remove(target + ".part")
                    server.events.put(("failed", name))
                    return self._reply(400, "Incomplete")
                os.replace(target + ".part", target)
                server.events.put(("received", target))
                return self._reply(200, "OK")

        for port in (PORT, 0):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
                break
            except OSError:
                continue
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.ip = lan_ip()
        threading.Thread(target=self.httpd.serve_forever, daemon=True,
                         name="send-http").start()
        self.discovery = None
        if receive:
            self.discovery = threading.Thread(target=self._answer_hellos,
                                              daemon=True, name="send-udp")
            self._udp_stop = False
            self.discovery.start()

    @property
    def url(self):
        return "http://%s:%d/?k=%s" % (self.ip, self.port, self.key)

    def page(self):
        files = ""
        if self.shared:
            rows = "".join(
                '<a class="f" href="/f/%d?k=%s" download>%s<span>%s</span></a>'
                % (i, self.key, html.escape(os.path.basename(p)),
                   _size(os.path.getsize(p)))
                for i, p in enumerate(self.shared))
            files = '<div class="card"><h2>Download</h2>%s</div>' % rows
        upload = ""
        if self.receive:
            upload = ('<div class="card"><h2>Send to this computer</h2>'
                      '<label class="b">Choose files<input type="file" multiple '
                      'onchange="send(this.files)"></label><div id="log"></div>'
                      '</div>')
        return PAGE % {"name": html.escape(device_name()), "files": files,
                       "upload": upload, "key": json.dumps(self.key)}

    def _answer_hellos(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError as exc:
            common.log("discovery bind: %r" % exc)
            return
        sock.settimeout(0.5)
        while not self._udp_stop:
            try:
                data, addr = sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if data == HELLO:
                reply = json.dumps({"app": "squint", "name": device_name(),
                                    "port": self.port}).encode()
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass
        sock.close()

    def stop(self):
        self._udp_stop = True
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


def find_devices(seconds=1.2):
    """Computers on this network with a Receive window open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.3)
    found = {}
    me = lan_ip()
    try:
        sock.sendto(HELLO, ("255.255.255.255", DISCOVERY_PORT))
        parts = me.split(".")
        if len(parts) == 4:
            sock.sendto(HELLO, (".".join(parts[:3] + ["255"]), DISCOVERY_PORT))
        end = time.time() + seconds
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            try:
                info = json.loads(data)
            except ValueError:
                continue
            if info.get("app") == "squint":
                found[addr[0]] = {"ip": addr[0], "name": info.get("name", "?"),
                                  "port": int(info.get("port", PORT))}
    finally:
        sock.close()
    return list(found.values())


def push(device, files, progress=None):
    """Offer `files` to a device, wait for it to say yes, send them."""
    base = "http://%s:%d" % (device["ip"], device["port"])
    offer = {"from": device_name(),
             "files": [{"name": os.path.basename(f),
                        "size": os.path.getsize(f)} for f in files]}
    req = urllib.request.Request(base + "/offer", json.dumps(offer).encode(),
                                 {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=75) as resp:
            ticket = json.loads(resp.read())["ticket"]
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError("%s said no" % device["name"])
        raise
    total = sum(os.path.getsize(f) for f in files) or 1
    sent = 0
    for path in files:
        size = os.path.getsize(path)

        def body(path=path):
            nonlocal sent
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(CHUNK)
                    if not chunk:
                        return
                    sent += len(chunk)
                    if progress:
                        progress.set(sent / float(total), "Sending %s"
                                     % os.path.basename(path))
                    yield chunk

        url = "%s/put?k=%s&name=%s" % (base, ticket, urllib.parse.quote(
            os.path.basename(path)))
        req = urllib.request.Request(url, data=body(), method="POST",
                                     headers={"Content-Length": str(size)})
        with opener.open(req, timeout=120) as resp:
            if resp.status != 200:
                raise RuntimeError("sending %s failed" % os.path.basename(path))
    return len(files)


# -- windows ---------------------------------------------------------------

class ShareWindow:
    """The QR code, the address, and what has come and gone."""

    def __init__(self, ctrl, title, intro, shared=(), receive=True):
        self.ctrl = ctrl
        self.events = queue.Queue()
        self.server = Server(shared, receive, self.events)
        self.server.ask = self._ask
        self.pending = []
        win = self.win = tk.Toplevel(ctrl.root)
        win.title(title)
        win.configure(bg=common.BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close)
        frame = tk.Frame(win, bg=common.BG, padx=22, pady=18)
        frame.pack()
        tk.Label(frame, text=title, bg=common.BG, fg=common.TEXT,
                 font=(common.FONT, 13, "bold")).pack(anchor="w")
        tk.Label(frame, text=intro, bg=common.BG, fg=common.MUTED,
                 font=(common.FONT, 9), justify="left",
                 wraplength=300).pack(anchor="w", pady=(2, 12))
        canvas = tk.Canvas(frame, width=240, height=240, bg="#FFFFFF",
                           highlightthickness=0)
        canvas.pack()
        qr.draw(canvas, self.server.url, 0, 0, 240)
        tk.Label(frame, text=self.server.url, bg=common.BG, fg=common.MUTED,
                 font=(common.FONT, 8)).pack(pady=(8, 0))
        visible = ("Other computers see this one as “%s” while this window "
                   "is open." % device_name()) if receive else ""
        if visible:
            tk.Label(frame, text=visible, bg=common.BG, fg=common.MUTED,
                     font=(common.FONT, 9), wraplength=300,
                     justify="left").pack(anchor="w", pady=(10, 0))
        self.status = tk.Label(frame, text="Same Wi-Fi only. Waiting…",
                               bg=common.BG, fg=common.TEXT,
                               font=(common.FONT, 10), wraplength=300,
                               justify="left")
        self.status.pack(anchor="w", pady=(10, 0))
        buttons = tk.Frame(frame, bg=common.BG)
        buttons.pack(anchor="e", pady=(14, 0))
        if receive:
            common._button(buttons, "Open folder", lambda: common.reveal(
                common.received_dir())).pack(side="left", padx=(0, 8))
        common._button(buttons, "Done", self.close, primary=True).pack(
            side="left")
        self.received = []
        common._center(win)
        self._poll()

    def _ask(self, offer):
        """Runs on a server thread: hand the question to Tk, wait."""
        box = queue.Queue()
        self.pending.append((offer, box))
        try:
            return box.get(timeout=60)
        except queue.Empty:
            return False

    def _poll(self):
        try:
            while self.pending:
                offer, box = self.pending.pop(0)
                files = offer.get("files", [])
                size = sum(int(f.get("size", 0)) for f in files)
                names = ", ".join(f.get("name", "?") for f in files[:3])
                if len(files) > 3:
                    names += " and %d more" % (len(files) - 3)
                answer = common.ask_choice(
                    self.ctrl.root, "Incoming files",
                    "%s wants to send %d file%s (%s):\n%s" % (
                        offer.get("from", "A computer"), len(files),
                        "" if len(files) == 1 else "s", _size(size), names),
                    [("yes", "Accept"), ("no", "Decline")])
                box.put(answer == "yes")
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "receiving":
                    _k, name, got, total = event
                    pct = int(100 * got / total) if total else 0
                    self.status.configure(text="Receiving %s  %d%%" % (name,
                                                                        pct))
                elif kind == "received":
                    self.received.append(event[1])
                    self.status.configure(
                        text="Received %d file%s → Downloads\\Squint\\Received"
                        % (len(self.received),
                           "" if len(self.received) == 1 else "s"))
                elif kind == "sent":
                    self.status.configure(text="Downloaded: %s" % event[1])
                elif kind == "failed":
                    self.status.configure(text="%s did not arrive completely."
                                          % event[1])
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.win.after(150, self._poll)

    def close(self):
        self.server.stop()
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.received:
            common.tell(self.ctrl, "%d file%s received." % (
                len(self.received), "" if len(self.received) == 1 else "s"),
                self.received[-1])


def receive_cmd(ctrl, **_):
    ShareWindow(ctrl, "Receive files",
                "Scan with a phone to send from it, or pick this computer "
                "under Send on another one.", receive=True)


def phone_cmd(ctrl, selection=None, anchor=None, **_):
    files = [p for p in (selection or []) if os.path.isfile(p)]

    def open_window(files):
        ShareWindow(ctrl, "Phone via QR",
                    "Scan with the phone's camera. Phone and computer must "
                    "be on the same Wi-Fi.", shared=files, receive=True)

    if files:
        open_window(files)
        return
    from .card import Card
    card = Card(ctrl, "Phone via QR", anchor)

    def start(values):
        card.close()
        chosen = []
        if values["what"] == "send":
            chosen = common.pick_files(ctrl, "Files for the phone",
                                       [("All files", "*.*")])
            if not chosen:
                return
        open_window(chosen)

    card.form([{"kind": "choice", "key": "what", "label": "What to do",
                "options": [("send", "Send to phone"),
                            ("get", "Get from phone")],
                "default": "get"}], "Show QR code", start)


def nearby_cmd(ctrl, selection=None, anchor=None, **_):
    files = common.pick_files(ctrl, "Files to send", [("All files", "*.*")],
                              selection=[p for p in (selection or [])
                                         if os.path.isfile(p)])
    if not files:
        return
    win = tk.Toplevel(ctrl.root)
    win.title("Send to a nearby device")
    win.configure(bg=common.BG)
    win.attributes("-topmost", True)
    frame = tk.Frame(win, bg=common.BG, padx=22, pady=18)
    frame.pack()
    tk.Label(frame, text="Send %d file%s to" % (len(files), "" if len(files) == 1
                                                 else "s"),
             bg=common.BG, fg=common.TEXT,
             font=(common.FONT, 13, "bold")).pack(anchor="w")
    tk.Label(frame, text="Open Receive on the other computer. Same Wi-Fi only.",
             bg=common.BG, fg=common.MUTED, font=(common.FONT, 9)).pack(
        anchor="w", pady=(2, 10))
    listing = tk.Frame(frame, bg=common.BG)
    listing.pack(fill="x")
    searching = tk.Label(frame, text="Looking…", bg=common.BG, fg=common.MUTED,
                         font=(common.FONT, 9))
    searching.pack(anchor="w", pady=(8, 0))
    common._button(frame, "Cancel", win.destroy).pack(anchor="e", pady=(12, 0))
    shown = {}

    def choose(device):
        win.destroy()
        from .card import Card
        card = Card(ctrl, "Send to %s" % device["name"], None,
                    "%d file%s" % (len(files), "" if len(files) == 1 else "s"))

        class Bar:
            def set(self, fraction, text=None):
                card.progress(fraction, text)

        def work(p):
            p(None, "Waiting for %s to accept" % device["name"])
            return push(device, files, Bar())

        card.run(work, lambda n: ("Sent %d file%s" % (
            n, "" if n == 1 else "s"), None),
            "Sending to %s…" % device["name"])

    def look():
        if not win.winfo_exists():
            return
        common.in_background(ctrl, find_devices, show, "Looking for devices")

    def show(devices):
        try:
            if not win.winfo_exists():
                return
        except tk.TclError:
            return
        for d in devices:
            if d["ip"] not in shown:
                b = common._button(listing, "%s   (%s)" % (d["name"], d["ip"]),
                                   lambda d=d: choose(d))
                b.configure(anchor="w", width=36)
                b.pack(fill="x", pady=2)
                shown[d["ip"]] = b
        searching.configure(text="Looking…" if not shown else "")
        win.after(1500, look)

    common._center(win)
    look()
