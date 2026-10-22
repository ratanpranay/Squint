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


def computer_name():
    if common.IS_MAC:
        try:
            done = common.run(["scutil", "--get", "ComputerName"], timeout=3)
            name = done.stdout.decode("utf-8", "replace").strip()
            if name:
                return name
        except Exception:
            pass
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def device_name():
    """What other people see: the nickname, or the computer's name."""
    return (common.setting("nickname") or "").strip() or computer_name()


# -- Windows Firewall ----------------------------------------------------
#
# Other devices have to reach this computer. Windows asks "Allow access?"
# the first time - a prompt that easily ends up behind the ring, and that,
# dismissed, leaves a rule that blocks Squint for good. One elevated step
# replaces whatever is there with a rule that lets Squint in.

RULE = "Squint"


def firewall_ok():
    if not common.IS_WINDOWS:
        return True
    try:
        done = common.run(["netsh", "advfirewall", "firewall", "show", "rule",
                           "name=" + RULE], timeout=8)
        return done.returncode == 0
    except Exception:
        return True                  # cannot tell; do not nag


def allow_firewall():
    """Ask Windows (one UAC prompt) to let Squint accept connections."""
    import base64
    import sys
    folder = os.path.dirname(sys.executable)
    programs = [os.path.join(folder, n) for n in ("pythonw.exe", "python.exe")
                if os.path.isfile(os.path.join(folder, n))] or [sys.executable]
    lines = ["$ErrorActionPreference='SilentlyContinue'"]
    for prog in programs:
        q = prog.replace("'", "''")
        lines.append(
            "Get-NetFirewallApplicationFilter -Program '%s' | "
            "Get-NetFirewallRule | Where-Object { $_.Direction -eq 'Inbound' "
            "-and $_.Action -eq 'Block' } | Remove-NetFirewallRule" % q)
    lines.append("Remove-NetFirewallRule -DisplayName '%s'" % RULE)
    for prog in programs:
        q = prog.replace("'", "''")
        lines.append("New-NetFirewallRule -DisplayName '%s' -Direction "
                     "Inbound -Program '%s' -Action Allow -Profile Any "
                     "| Out-Null" % (RULE, q))
    script = ";".join(lines)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    common.run(["powershell", "-NoProfile", "-Command",
                "Start-Process powershell -Verb RunAs -Wait -WindowStyle "
                "Hidden -ArgumentList '-NoProfile','-EncodedCommand','%s'"
                % encoded], timeout=180)
    return firewall_ok()


def firewall_row(ctrl, menu, frame):
    """A warning with an Allow button, only when the rule is missing."""
    if firewall_ok():
        return
    s = menu.s
    box = tk.Frame(frame, bg="#3A3320")
    box.pack(fill="x", pady=(0, int(8 * s)))
    text = tk.Label(box, text="Windows may stop other devices reaching this "
                    "PC. Allow it once (Windows asks to confirm).",
                    bg="#3A3320", fg="#F5D58A", font=menu.f(11),
                    justify="left", anchor="w",
                    wraplength=menu.panel_width() - int(90 * s),
                    padx=int(8 * s), pady=int(6 * s))
    text.pack(side="left", fill="x", expand=True)

    def allow():
        button.configure(text="…", state="disabled")

        def done(ok):
            try:
                if ok:
                    box.destroy()
                    menu.relayout()
                else:
                    text.configure(text="Not allowed yet. If Windows asked, "
                                   "choose Yes; on a work PC the IT "
                                   "department may need to do it.")
                    button.configure(text="Try again", state="normal")
            except tk.TclError:
                pass

        common.in_background(ctrl, allow_firewall, done, "Allowing Squint")

    button = menu.button(box, "Allow", allow, primary=True)
    button.configure(padx=int(10 * s), pady=int(4 * s))
    button.pack(side="right", padx=int(6 * s))


def name_row(menu, frame):
    """Above the Send actions: the name others see, and Change."""
    s = menu.s
    row = tk.Frame(frame, bg=common.PANEL)
    row.pack(fill="x", pady=(0, int(6 * s)))

    def show():
        for child in row.winfo_children():
            child.destroy()
        tk.Label(row, text="You appear as", bg=common.PANEL, fg=common.MUTED,
                 font=menu.f(11)).pack(side="left")
        tk.Label(row, text=device_name(), bg=common.PANEL, fg="#FFFFFF",
                 font=menu.f(11, True)).pack(side="left", padx=int(6 * s))
        change = tk.Label(row, text="Change", bg=common.PANEL,
                          fg="#8FB4FF", font=menu.f(11), cursor="hand2")
        change.pack(side="right")
        change.bind("<Button-1>", lambda _e: edit())
        menu.relayout()

    def edit():
        for child in row.winfo_children():
            child.destroy()
        var = tk.StringVar(value=device_name())
        entry = tk.Entry(row, textvariable=var, bg=common.ROW, fg=common.TEXT,
                         relief="flat", highlightthickness=0,
                         insertbackground=common.TEXT, font=menu.f(11))
        entry.pack(side="left", fill="x", expand=True, ipady=int(4 * s))

        def save(_e=None):
            name = var.get().strip()[:40]
            common.set_setting("nickname", name)
            show()

        entry.bind("<Return>", save)
        entry.bind("<Escape>", lambda _e: (show(), "break")[1])
        b = menu.button(row, "Save", save, primary=True)
        b.configure(padx=int(10 * s), pady=int(3 * s))
        b.pack(side="left", padx=(int(4 * s), 0))
        entry.focus_set()
        entry.select_range(0, "end")
        menu.relayout()

    show()


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


# -- in the ring's panel ---------------------------------------------------
#
# Send, Receive and Phone all show in the panel beside the ring; the QR
# code is drawn in the middle of the ring itself (menu.set_qr).

def _share_view(ctrl, menu, title, intro, shared=()):
    """The QR code in the ring, what is happening in the panel."""
    events = queue.Queue()
    server = Server(shared, True, events)
    pending = []
    received = []

    def ask(offer):                     # on a server thread
        box = queue.Queue()
        pending.append((offer, box))
        try:
            return box.get(timeout=60)
        except queue.Empty:
            return False

    server.ask = ask

    def stop():
        server.stop()
        for _offer, box in pending:
            box.put(False)
        if received:
            common.tell(ctrl, "%d file%s received." % (
                len(received), "" if len(received) == 1 else "s"),
                received[-1])

    def build(frame):
        s = menu.s
        menu.on_clear(stop)
        menu.set_qr(server.url)
        menu.header(frame, title, close=True)
        firewall_row(ctrl, menu, frame)
        tk.Label(frame, text=intro, bg=common.PANEL, fg=common.MUTED,
                 font=menu.f(11), justify="left", anchor="w",
                 wraplength=menu.panel_width()).pack(fill="x")
        status = tk.Label(frame, text="Waiting…  (same Wi-Fi only)",
                          bg=common.PANEL, fg=common.TEXT, font=menu.f(11),
                          justify="left", anchor="w",
                          wraplength=menu.panel_width())
        status.pack(fill="x", pady=(int(10 * s), 0))
        ask_area = tk.Frame(frame, bg=common.PANEL)
        ask_area.pack(fill="x")
        menu.note(frame, "Others see you as “%s”. Files go to "
                  "Downloads\\Squint\\Received.\nNot connecting? Both "
                  "must be on the same Wi-Fi; guest and office Wi-Fi often "
                  "block devices talking to each other." % device_name())
        row = tk.Frame(frame, bg=common.PANEL)
        row.pack(fill="x", pady=(int(10 * s), 0))
        menu.button(row, "Done", menu.back, primary=True).pack(side="right")
        menu.button(row, "Open folder", lambda: common.reveal(
            common.received_dir())).pack(side="right", padx=(0, int(6 * s)))
        asking = {"box": None}

        def answer(yes):
            box = asking["box"]
            asking["box"] = None
            for child in ask_area.winfo_children():
                child.destroy()
            if box is not None:
                box.put(yes)
            status.configure(text="Accepted. Receiving…" if yes
                             else "Declined.")
            menu.relayout()

        def poll():
            if menu.closed or not frame.winfo_exists():
                return
            if pending and asking["box"] is None:
                offer, box = pending.pop(0)
                asking["box"] = box
                files = offer.get("files", [])
                size = sum(int(f.get("size", 0)) for f in files)
                names = ", ".join(f.get("name", "?") for f in files[:3])
                if len(files) > 3:
                    names += " and %d more" % (len(files) - 3)
                tk.Label(ask_area, text="%s wants to send %d file%s (%s)\n%s"
                         % (offer.get("from", "A computer"), len(files),
                            "" if len(files) == 1 else "s", _size(size),
                            names), bg=common.ROW, fg=common.TEXT,
                         font=menu.f(11), justify="left", anchor="w",
                         wraplength=menu.panel_width() - int(16 * s),
                         padx=int(8 * s), pady=int(6 * s)).pack(
                    fill="x", pady=(int(8 * s), int(4 * s)))
                buttons = tk.Frame(ask_area, bg=common.PANEL)
                buttons.pack(fill="x")
                menu.button(buttons, "Accept", lambda: answer(True),
                            primary=True).pack(side="right")
                menu.button(buttons, "Decline", lambda: answer(False)).pack(
                    side="right", padx=(0, int(6 * s)))
                menu.relayout()
            try:
                while True:
                    event = events.get_nowait()
                    kind = event[0]
                    if kind == "receiving":
                        _k, name, got, total = event
                        status.configure(text="Receiving %s  %d%%" % (
                            name, int(100 * got / total) if total else 0))
                    elif kind == "received":
                        received.append(event[1])
                        status.configure(text="✓ Received %d file%s" % (
                            len(received), "" if len(received) == 1 else "s"))
                    elif kind == "sent":
                        status.configure(text="✓ Downloaded to the phone: %s"
                                         % event[1])
                    elif kind == "failed":
                        status.configure(text="%s did not arrive completely."
                                         % event[1])
            except queue.Empty:
                pass
            ctrl.root.after(150, poll)

        poll()

    menu.show_view(build, pinned=True, name="send")


def receive_cmd(ctrl, menu=None, **_):
    _share_view(ctrl, menu, "Receive files",
                "Scan the code with a phone's camera to send from it, or "
                "pick this computer under Send on another one.")


def phone_cmd(ctrl, selection=None, menu=None, **_):
    files = [p for p in (selection or []) if os.path.isfile(p)]
    if files:
        _share_view(ctrl, menu, "Phone via QR",
                    "Scan the code with the phone's camera to download %s, "
                    "or send files from the phone." % (
                        "this file" if len(files) == 1
                        else "these %d files" % len(files)), files)
        return

    def build(frame):
        menu.header(frame, "Phone via QR", close=True)

        def send_to_phone():
            chosen = common.pick_files(ctrl, "Files for the phone",
                                       [("All files", "*.*")])
            if chosen:
                phone_cmd(ctrl, chosen, menu)

        menu.row(frame, "Send files to my phone", send_to_phone, "A")
        menu.row(frame, "Get files from my phone", lambda: _share_view(
            ctrl, menu, "Phone via QR", "Scan the code with the phone's "
            "camera, then choose the photos or files to send."), "B")
        menu.note(frame, "Phone and computer must be on the same Wi-Fi.")

    menu.show_view(build, pinned=True, name="phone")


def nearby_cmd(ctrl, selection=None, menu=None, **_):
    files = common.pick_files(ctrl, "Files to send", [("All files", "*.*")],
                              selection=[p for p in (selection or [])
                                         if os.path.isfile(p)])
    if not files:
        return
    token = object()
    state = {"token": token, "shown": {}}

    def choose(device):
        from .card import Card
        card = Card(ctrl, "Send to %s" % device["name"], None,
                    "%d file%s" % (len(files), "" if len(files) == 1 else "s"),
                    host=menu)

        class Bar:
            def set(self, fraction, text=None):
                card.progress(fraction, text)

        def work(p):
            p(None, "Waiting for %s to accept" % device["name"])
            return push(device, files, Bar())

        card.run(work, lambda n: ("Sent %d file%s" % (
            n, "" if n == 1 else "s"), None),
            "Sending to %s…" % device["name"])

    def build(frame):
        s = menu.s
        menu.header(frame, "Send %d file%s to" % (
            len(files), "" if len(files) == 1 else "s"), close=True)
        listing = tk.Frame(frame, bg=common.PANEL)
        listing.pack(fill="x")
        searching = tk.Label(frame, text="Looking for computers…",
                             bg=common.PANEL, fg=common.MUTED,
                             font=menu.f(11), anchor="w")
        searching.pack(fill="x", pady=(int(4 * s), 0))
        menu.note(frame, "Open Squint's Receive on the other computer. "
                  "Same Wi-Fi only.")
        menu.on_clear(lambda: state.update(token=None))

        def show(devices):
            if state["token"] is not token or menu.closed:
                return
            changed = False
            for d in devices:
                if d["ip"] not in state["shown"]:
                    state["shown"][d["ip"]] = menu.row(
                        listing, "%s   %s" % (d["name"], d["ip"]),
                        lambda d=d: choose(d))
                    changed = True
            searching.configure(text="" if state["shown"]
                                else "Looking for computers…")
            if changed:
                menu.relayout()
            ctrl.root.after(1500, look)

        def look():
            if state["token"] is token and not menu.closed:
                common.in_background(ctrl, find_devices, show,
                                     "Looking for devices")

        look()

    menu.show_view(build, pinned=True, name="nearby")
