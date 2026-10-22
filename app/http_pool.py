"""HTTP requests that keep the connection open between them.

Every translation is one small request to a server that is usually on
another continent, and until now each one opened a brand-new connection.
`urllib.request.urlopen` is the one-liner everybody reaches for and it does
exactly one thing: connect, fetch, close. It has no way to stay on the
line. Nothing decided to hang up — the tool has no other mode.

The cost is paid before a single character of the sentence goes out:

    look up where the host is          one round trip, if not cached
    open the connection (TCP)          one round trip
    agree on the encryption (TLS)      one or two more

To a server 100ms away that is a third of a second of nothing happening,
on every press of the shortcut, for ever. Held open, the second request
onwards skips all of it and the sentence leaves immediately.

This is deliberately small and deliberately boring. It is not a general
HTTP client and it is not a dependency: `http.client` is in the standard
library and does support keep-alive, it just has to be driven by hand.

Two things it must get right, because both are ways to be slower or more
broken than what it replaces:

A POOLED CONNECTION CAN BE DEAD. Servers close connections that have sat
idle, and they do not announce it — the socket looks fine until a request
is written to it and nothing comes back. So a failure on a *reused*
connection is retried once on a fresh one, and a failure on a fresh
connection is a real failure and is raised. The retry only happens when
nothing was read back, which is what a dead idle socket looks like; a
request that got a reply is never sent twice.

SOME PEOPLE ARE BEHIND A PROXY. urlopen reads the system proxy settings
and this does not, so where a proxy is configured for the host this steps
aside and lets urlopen do it exactly as before. A quarter of a second is
not worth being the app that stopped working at the office.

It raises what urlopen raises — `urllib.error.HTTPError` for a status the
caller should see, `urllib.error.URLError` for anything that went wrong
below that — so every caller's existing error handling still applies. That
is a requirement, not a nicety: `translator` reads `exc.reason` to spot a
certificate failure and retry with a different trust store, and
`ocr_google` reads `exc.code`.
"""
import http.client
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# How long a connection may sit unused before it is thrown away rather than
# risked. Servers commonly close an idle connection at 60 seconds and say
# nothing, so this stays under that: below it the reuse is nearly always
# good, above it the retry below would be doing all the work anyway.
IDLE_LIMIT = 20.0

# How long a *reused* connection gets to start answering a GET before it is
# taken for dead and the request is sent again on a fresh one.
#
# Some networks - office firewalls especially - forget an idle connection
# without telling either end. Nothing is refused and nothing is reset: the
# request goes out and the answer never comes, so the only way to find out
# is to wait. The retry below existed, but it was waiting the caller's full
# timeout first. Measured on such a network: the first snip of a session
# took 16 seconds, and one request in the log had been "held" for 10.9 of
# them. A translation GET answers in a few hundred milliseconds, so two
# seconds of silence on a reused socket is the dead-socket case, and a GET
# can be sent twice without harm. A POST keeps the full timeout: it may be
# a language model thinking, and it must not be sent twice.
REUSED_GRACE = 2.0

# And a POST cannot have that grace: it may be a language model thinking for
# several seconds, and it must never be sent twice. So a POST reuses only a
# connection that was busy moments ago - too recently for a firewall to
# have forgotten it - and otherwise pays for a fresh one, a few hundred
# milliseconds, rather than risk the whole timeout on a dead one.
POST_IDLE_LIMIT = 5.0

# Per host. Requests here are made one at a time from the shortcut, plus
# an occasional background check, so this is about not leaking sockets
# rather than about throughput.
POOL_LIMIT = 4


class _Pool:
    """Idle connections, by where they go and what they trust."""

    def __init__(self):
        self._lock = threading.Lock()
        self._idle = {}
        # Counting connections is the only way to prove from the outside
        # that anything is being reused at all — the whole feature is
        # invisible otherwise, and an optimisation nobody can see the
        # absence of is one that quietly stops working. The tests read
        # `opened`; `summary()` is what the log reads.
        self.opened = 0
        self.fresh = [0, 0.0]
        self.kept = [0, 0.0]

    def took(self, started, reused):
        spent = max(0.0, time.time() - started)
        with self._lock:
            tally = self.kept if reused else self.fresh
            tally[0] += 1
            tally[1] += spent

    def summary(self):
        """"12 requests, 3 dialled (avg 412ms), 9 held (avg 138ms)".

        Written to the log when the app closes rather than per request: it
        is the comparison that says anything, and one line at the end says
        it better than a hundred lines nobody adds up. It is also the only
        way to see the saving on a real network, since neither number can
        be guessed from here.
        """
        with self._lock:
            fresh, kept = list(self.fresh), list(self.kept)
        total = fresh[0] + kept[0]
        if not total:
            return ""

        def average(tally):
            return (tally[1] / tally[0] * 1000.0) if tally[0] else 0.0

        return ("%d requests, %d dialled (avg %.0fms), %d held (avg %.0fms)"
                % (total, fresh[0], average(fresh),
                   kept[0], average(kept)))

    def take(self, key, limit=None):
        """An idle connection for `key`, or None.

        `limit` is how long it may have sat idle; IDLE_LIMIT if not given.
        """
        limit = IDLE_LIMIT if limit is None else limit
        now = time.time()
        with self._lock:
            waiting = self._idle.get(key) or []
            while waiting:
                connection, parked = waiting.pop()
                if now - parked <= limit:
                    self._idle[key] = waiting
                    return connection
                _shut(connection)
            self._idle[key] = waiting
        return None

    def give_back(self, key, connection):
        with self._lock:
            waiting = self._idle.setdefault(key, [])
            if len(waiting) >= POOL_LIMIT:
                _shut(connection)
                return
            waiting.append((connection, time.time()))

    def made_one(self):
        with self._lock:
            self.opened += 1

    def clear(self):
        with self._lock:
            for waiting in self._idle.values():
                for connection, _parked in waiting:
                    _shut(connection)
            self._idle = {}


POOL = _Pool()


def _shut(connection):
    try:
        connection.close()
    except Exception:
        pass


def proxied(url):
    """Whether the system says this host goes through a proxy.

    Both halves matter: a proxy set for the scheme, and `no_proxy` letting
    this particular host past it. urlopen works that out itself, so where
    the answer is yes the request is handed back to urlopen entirely.
    """
    try:
        found = urllib.request.getproxies() or {}
    except Exception:
        return False
    parts = urllib.parse.urlsplit(url)
    if not found.get(parts.scheme):
        return False
    try:
        return not urllib.request.proxy_bypass(parts.hostname or "")
    except Exception:
        # Cannot tell — assume the proxy applies. Being slower is a much
        # smaller failure than not reaching the network at all.
        return True


def _connect(parts, timeout, context):
    if parts.scheme == "https":
        return http.client.HTTPSConnection(
            parts.hostname, parts.port, timeout=timeout, context=context)
    return http.client.HTTPConnection(parts.hostname, parts.port,
                                      timeout=timeout)


def _open(pool, parts, timeout, context):
    connection = _connect(parts, timeout, context)
    pool.made_one()
    return connection


def _deadline(connection, timeout):
    """Apply this call's timeout to a connection made for an earlier one."""
    connection.timeout = timeout
    socket = getattr(connection, "sock", None)
    if socket is not None:
        try:
            socket.settimeout(timeout)
        except Exception:
            pass


def _target(parts):
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return path


def _send(connection, method, parts, data, headers, timeout):
    _deadline(connection, timeout)
    connection.request(method, _target(parts), body=data, headers=headers)
    response = connection.getresponse()
    body = response.read()
    return response, body


def fetch(url, data=None, headers=None, timeout=10, context=None,
          method=None, pool=None):
    """The body of `url`, as bytes, over a connection kept for next time.

    A drop-in for `urlopen(...).read()`: same arguments that matter, same
    two exceptions, and the same behaviour where any of this cannot be done
    — a proxy, a scheme that is not http or https — because falling back is
    always allowed and failing is not.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or proxied(url):
        return _through_urlopen(url, data, headers, timeout, context)

    pool = pool or POOL
    method = method or ("POST" if data is not None else "GET")
    sending = dict(headers or {})
    sending.setdefault("Connection", "keep-alive")
    if data is not None:
        sending.setdefault("Content-Length", str(len(data)))
    key = (parts.scheme, parts.hostname, parts.port, context)

    started = time.time()
    connection = pool.take(key, None if method == "GET" else POST_IDLE_LIMIT)
    reused = connection is not None

    first_wait = timeout
    if reused and method == "GET" and timeout:
        first_wait = min(timeout, REUSED_GRACE)
    try:
        if connection is None:
            connection = _open(pool, parts, timeout, context)
        response, body = _send(connection, method, parts, data,
                               sending, first_wait)
    except Exception as exc:
        _shut(connection)
        if not reused:
            # A fresh connection that failed is the network failing. Sending
            # it again would only be slower about saying so.
            raise _as_url_error(exc)
        # A connection out of the pool that failed before answering is the
        # server having quietly closed it while it sat idle. That is this
        # module's own doing and the caller should never see it, so it is
        # paid for here — once.
        connection = None
        try:
            connection = _open(pool, parts, timeout, context)
            response, body = _send(connection, method, parts, data,
                                   sending, timeout)
        except Exception as second:
            _shut(connection)
            raise _as_url_error(second)

    pool.took(started, reused)
    if response.will_close:
        _shut(connection)
    else:
        pool.give_back(key, connection)

    if response.status >= 400:
        raise urllib.error.HTTPError(url, response.status, response.reason,
                                     response.headers, _Body(body))
    return body


def _as_url_error(exc):
    """Say it the way urlopen says it, so callers need no new handling."""
    if isinstance(exc, (urllib.error.HTTPError, urllib.error.URLError)):
        return exc
    return urllib.error.URLError(exc)


class _Body:
    """The already-read body, wearing the file-shaped face an HTTPError
    hands to whoever catches it.

    urllib gives the caller an unread stream. Here the body is read before
    the status is known — a response has to be read to the end before the
    connection can be used again — so what is handed over is what was read.
    """

    def __init__(self, raw):
        self._raw = raw

    def read(self, _size=-1):
        raw, self._raw = self._raw, b""
        return raw

    def close(self):
        pass


def _through_urlopen(url, data, headers, timeout, context):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout,
                                context=context) as response:
        return response.read()
