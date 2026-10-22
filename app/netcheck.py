"""Find out which part of the network is refusing, instead of guessing.

Three separate faults have now arrived at the user as the same red line
beside their API key: the service was busy, the service was slow, and — the
one this was written for — something between the app and Google. Each time
the visible evidence was identical and each time the honest answer was "I
do not know yet", which is not a thing to make someone rediscover by making
another key.

So this asks the four questions that have four different answers, in the
order they can fail, and reports where it stopped:

    1. Does the name resolve?          No  -> DNS, or the machine is offline.
    2. Does a TCP connection open?     No  -> a firewall is dropping it.
    3. Does TLS complete?              No  -> usually an intercepting proxy
                                              whose certificate Python does
                                              not trust. The browser trusts
                                              it, because the browser uses
                                              the Windows certificate store
                                              and Python uses certifi's.
                                              This is why a page can open in
                                              Brave while the app times out.
    4. Does the endpoint answer?       No  -> the service itself.

A browser opening the same address proves less than it looks. It uses a
different trust store, often a different proxy configuration, and it is
allowed through corporate filters that are set to block programmatic
clients. "It works in Chrome" and "it works from Python" are two questions.

Nothing here needs an API key: an unauthenticated request to a real
endpoint comes back 401 or 403, and that is a perfectly good answer — it
means every layer underneath is working.
"""
import socket
import time
import urllib.error
import urllib.request

HOST = "generativelanguage.googleapis.com"
PORT = 443
# A real endpoint, not "/". The root path has no page and answers 404 even
# when everything is working, which reads as a failure to anyone who tries
# it in a browser.
PROBE_PATH = "/v1beta/models"
TIMEOUT = 12


# Only the settings that decide where an HTTPS request goes. The
# environment of a developer machine is full of variables ending in
# "_proxy" that have nothing to do with this, and printing all of them
# buries the one line that matters in forty of noise.
PROXY_KEYS = ("https", "http", "no")


def proxies():
    """Whatever urllib will actually use for this host.

    Worth reporting: on Windows this comes from the same registry settings
    the browser uses, and a mismatch between what the browser does and what
    Python does is one of the few ways a page can open in Brave while the
    app cannot reach the same address.
    """
    try:
        found = urllib.request.getproxies() or {}
    except Exception:
        return {}
    return {key: found[key] for key in PROXY_KEYS if found.get(key)}


def _timed(step):
    start = time.time()
    try:
        detail = step()
        return True, detail, time.time() - start
    except Exception as exc:
        return False, exc, time.time() - start


def check(host=HOST, port=PORT, timeout=TIMEOUT):
    """Walk the layers. Returns (ok, [(name, ok, detail), ...])."""
    steps = []

    def dns():
        info = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        return ", ".join(sorted({item[4][0] for item in info}))[:80]

    ok, detail, seconds = _timed(dns)
    steps.append(("name lookup", ok,
                  ("%s  (%.1fs)" % (detail, seconds)) if ok else
                  "failed: %s — the machine may be offline, or DNS is "
                  "blocked" % detail))
    if not ok:
        return False, steps

    def connect():
        with socket.create_connection((host, port), timeout=timeout):
            return "connected"

    ok, detail, seconds = _timed(connect)
    steps.append(("connection", ok,
                  ("opened in %.1fs" % seconds) if ok else
                  "failed: %s — a firewall is refusing or dropping port "
                  "%d to this host" % (detail, port)))
    if not ok:
        return False, steps

    def handshake():
        from . import translator
        context = translator.ssl_context()
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return tls.version() or "TLS"

    ok, detail, seconds = _timed(handshake)
    if ok:
        steps.append(("secure connection", True,
                      "%s in %.1fs" % (detail, seconds)))
    else:
        note = str(detail)
        if "CERTIFICATE_VERIFY_FAILED" in note or "certificate" in note.lower():
            note += ("  — this is the signature of a company proxy that "
                     "opens encrypted traffic to inspect it. The browser "
                     "accepts it because Windows was told to trust the "
                     "company's certificate; Python was not, so the same "
                     "address opens in a browser and fails here.")
        steps.append(("secure connection", False, "failed: %s" % note))
        return False, steps

    def endpoint():
        request = urllib.request.Request(
            "https://%s%s" % (host, PROBE_PATH),
            headers={"User-Agent": "squint-netcheck"})
        try:
            from . import translator
            context = translator.ssl_context()
        except Exception:
            context = None
        try:
            with urllib.request.urlopen(request, timeout=timeout,
                                        context=context) as response:
                return "HTTP %s" % response.status
        except urllib.error.HTTPError as exc:
            # 401 and 403 are the expected answers without a key, and they
            # are good news: the request reached Google and Google replied.
            return "HTTP %s" % exc.code

    ok, detail, seconds = _timed(endpoint)
    if ok:
        code = str(detail)
        answered = any(part in code for part in ("200", "401", "403", "404"))
        steps.append(("the API answers", answered,
                      "%s in %.1fs%s" % (code, seconds,
                                         "" if answered else
                                         "  — unexpected, but it did reply")))
        return answered, steps
    steps.append(("the API answers", False, "failed: %s" % detail))
    return False, steps


def summary(host=HOST):
    """One block of text, for the diagnostics file and for Settings."""
    lines = ["Reaching %s" % host]
    found = proxies()
    lines.append("  proxy: %s" % (", ".join(
        "%s=%s" % (k, str(v)[:60]) for k, v in sorted(found.items()))
        or "none"))
    ok, steps = check(host)
    for name, good, detail in steps:
        lines.append("  %-18s %s  %s" % (name, "ok " if good else "FAIL",
                                         detail))
    lines.append("  => %s" % ("everything between this computer and Google "
                              "is working" if ok else
                              "stopped at the step marked FAIL above"))
    return ok, "\n".join(lines)
