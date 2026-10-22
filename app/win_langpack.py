"""Installing a Windows text-recognition pack, from inside the app.

This is the rung below every API key, and the only one that cannot run out.
Windows recognises exactly the languages it has packs for; a PC in an
English office has English, so pointed at Chinese it returns confident
nonsense. Cloud Vision fixes that and wants a credit card. Gemini fixes it
and wants a Google account and has a daily allowance. A Windows pack is
free, needs no account, no card, no network permission and no quota, and
once it is on the machine it is on the machine.

Until now the app could only describe where the setting was: "Settings ›
Time & language › Language & region › Add a language, then open that
language's options and install Optical character recognition." Six steps in
somebody else's app, after being told the thing they just tried does not
work. Most people stop.

Two things make it awkward, and both are told to the user before anything
starts rather than discovered by them afterwards:

  - It needs administrator rights. `Add-WindowsCapability` is a system
    change and Windows asks. On a company laptop the answer may simply be
    no, and then this cannot work at all — which is worth saying plainly
    rather than showing a failure that looks like a bug.
  - It takes minutes, not seconds. Windows downloads it.

Nothing here fetches anything itself. Windows does the downloading through
its own update channel, which is also why this does not trip the same
defences that blocked the old Python installer.
"""
import os
import re
import subprocess
import sys

# Language.OCR~~~zh-Hans-CN~0.0.1.0 — the middle field is the BCP-47 tag.
CAPABILITY = re.compile(r"^(Language\.OCR~~~([A-Za-z-]+)~[\d.]+)$", re.M)
LIST_TIMEOUT = 60
INSTALL_TIMEOUT = 15 * 60


def supported():
    return sys.platform == "win32"


def _run(args, timeout):
    """PowerShell, with no window and no profile.

    -NoProfile because a user profile that prints anything turns the
    output into something unparseable, and corporate profiles print
    plenty. CREATE_NO_WINDOW because a console flashing up in the middle
    of a settings panel looks like something has gone wrong.
    """
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags = subprocess.CREATE_NO_WINDOW
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command"] + args,
        capture_output=True, text=True, timeout=timeout,
        creationflags=flags)


# The OCR packs Windows offers, exactly as Windows names them.
#
# This list used to be invented, and the invention is what broke it. The
# tags were taken from the wrong vocabulary: zh-Hans-CN is what the OCR
# *engine* calls Chinese once the pack is on the machine, and the *pack*
# is called zh-CN. Squint asked Windows for Language.OCR~~~zh-Hans-CN,
# which does not exist, and the guessed list also carried hi-IN, th-TH,
# vi-VN, uk-UA and he-IL, none of which Windows has an OCR pack for at
# all — while missing bg-BG, es-MX, fr-CA, hr-HR, pt-PT, sk-SK, sl-SI,
# zh-HK and both Serbians, which it does.
#
# So this is now transcribed from Get-WindowsCapability on a real machine
# rather than reasoned out. It is the standard Features-on-Demand set and
# is the same on every Windows 10 and 11 edition; a name is still checked
# against the machine before anything is installed, so a wrong one here
# is reported rather than acted on.
KNOWN_TAGS = (
    "ar-SA", "bg-BG", "bs-LATN-BA", "cs-CZ", "da-DK", "de-DE", "el-GR",
    "en-GB", "en-US", "es-ES", "es-MX", "fi-FI", "fr-CA", "fr-FR",
    "hr-HR", "hu-HU", "it-IT", "ja-JP", "ko-KR", "nb-NO", "nl-NL",
    "pl-PL", "pt-BR", "pt-PT", "ro-RO", "ru-RU", "sk-SK", "sl-SI",
    "sr-CYRL-RS", "sr-LATN-RS", "sv-SE", "tr-TR", "zh-CN", "zh-HK",
    "zh-TW",
)

last_note = ""

# Kept apart from last_note on purpose. What PowerShell prints when it
# refuses is "Get-WindowsCapability : The requested operation requires
# elevation." — useful in a bug report, meaningless in a settings panel,
# and it was being pasted into the note truncated at 120 characters, so
# it arrived on screen as "(Get-WindowsCapability : The" and read as a
# crash rather than as the harmless refusal it is.
last_error = ""


def _installed_tags():
    """What this machine can already read, asked without elevation.

    The OCR engine itself will say which languages it has, and answering
    that needs no administrator rights at all — which is the whole reason
    it is used here rather than the capability list.
    """
    try:
        from . import ocr_windows
        return {str(tag).lower() for tag in ocr_windows.available_languages()}
    except Exception:
        return set()


def _parts(tag):
    """(language, script, region), lowercased. Any of them may be empty.

    A four-letter alphabetic subtag is a script — Hans, Hant, Cyrl, Latn —
    and anything else after the language is the region. Windows writes
    them in different cases in different places (sr-CYRL-RS as a pack,
    sr-Cyrl-RS as a recognised language), which is why nothing here
    compares strings directly.
    """
    bits = [bit for bit in str(tag or "").replace("_", "-").split("-") if bit]
    language = bits[0].lower() if bits else ""
    script = region = ""
    for bit in bits[1:]:
        if len(bit) == 4 and bit.isalpha():
            script = bit.lower()
        else:
            region = bit.lower()
    return language, script, region


def same_language(one, other):
    """Whether two tags name the same thing, across the two vocabularies.

    The pack is zh-CN and the engine then reports zh-Hans-CN; the pack is
    sr-CYRL-RS and the engine reports sr-Cyrl-RS. Comparing the strings
    says no to both, which is how a pack that had just been installed went
    on being offered as something to install.

    The rule: the language must match, and a script or region must match
    only when both sides give one. So zh-CN and zh-Hans-CN are the same
    language, zh-CN and zh-Hant-TW are not, and sr-CYRL-RS and sr-Latn-RS
    are not either — those really are two different packs.
    """
    la, sa, ra = _parts(one)
    lb, sb, rb = _parts(other)
    if not la or la != lb:
        return False
    if sa and sb and sa != sb:
        return False
    if ra and rb and ra != rb:
        return False
    return True


def _matches_installed(tag, installed):
    return any(same_language(tag, have) for have in installed)


def available_packs():
    """[(tag, capability, installed)] for every OCR pack Windows offers.

    Asking Windows properly needs administrator rights — which is not what
    the first version of this assumed. Get-WindowsCapability -Online is a
    servicing call, and without elevation it fails; the failure was caught
    and turned into an empty list, so a machine that offers a dozen packs
    reported that it offered none. That is a worse answer than a guess,
    because it is a confident one.

    So: ask, and if the answer is nothing, fall back to the list of names
    that Windows uses anyway. What is *already installed* comes from the
    OCR engine itself, which answers without elevation.
    """
    global last_note, last_error
    last_note = last_error = ""
    if not supported():
        return []

    installed = _installed_tags()
    packs, failed = [], ""
    try:
        done = _run(["Get-WindowsCapability -Online | "
                     "Where-Object { $_.Name -like 'Language.OCR*' } | "
                     "ForEach-Object { \"$($_.Name)|$($_.State)\" }"],
                    LIST_TIMEOUT)
        for line in (done.stdout or "").splitlines():
            name, _, state = line.strip().partition("|")
            found = CAPABILITY.match(name)
            if not found:
                continue
            packs.append((found.group(2), found.group(1),
                          state.strip().lower() == "installed"))
        failed = (done.stderr or "").strip()
    except Exception as exc:
        failed = str(exc)

    if packs:
        return packs

    # Nothing came back. Either this edition really has none — which is
    # rare — or Windows would not answer without elevation, which is
    # common and is not worth a UAC prompt just to draw a list.
    last_note = ("Windows would not list its packs without administrator "
                 "rights, so this is the standard Windows list. Anything "
                 "this edition does not have is checked before it is "
                 "installed and reported plainly.")
    last_error = failed
    return [(tag, "Language.OCR~~~%s~0.0.1.0" % tag,
             _matches_installed(tag, installed))
            for tag in KNOWN_TAGS]


def pack_for(tag, packs=None):
    """The capability that would let Windows read `tag`, or None.

    Matched on the language part, not the whole string: the app asks for
    zh-Hans-CN and Windows may offer zh-Hans, or the other way round, and
    refusing to match those would report "no pack available" about a pack
    that is sitting right there.
    """
    if not tag:
        return None
    packs = available_packs() if packs is None else packs
    matches = [pack for pack in packs if same_language(tag, pack[0])]
    if not matches:
        return None
    # Chinese has three packs and Windows lists them alphabetically, so
    # asking for "zh" alone would otherwise get zh-CN by accident rather
    # than on purpose. A region that was actually asked for wins.
    wanted = _parts(tag)
    matches.sort(key=lambda pack: 0 if _parts(pack[0])[2] == wanted[2] else 1)
    return matches[0]


def is_admin():
    if not supported():
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


NEEDS_ADMIN = (
    "Windows needs permission to install a language pack, so it will ask. "
    "If this is a work computer that refuses, the pack has to be added by "
    "whoever looks after it — nothing the app can do gets round that. "
    "Everything else in Squint keeps working meanwhile.")


# What the elevated shell reports back, as exit codes. It runs hidden and
# its output goes nowhere the parent can read, so the exit code is the
# whole channel and it has to say more than "PowerShell ran".
DONE = 0                 # installed, and Windows confirms it
ALREADY = 10             # it was already there
NOT_CONFIRMED = 11       # the command was accepted, the pack still is not on
FAILED = 12              # Add-WindowsCapability itself failed
NO_SUCH_PACK = 13        # this edition does not offer it

# try/catch around each step and an explicit exit for every outcome.
#
# This is the fix for the bug that made a failed install read as a
# successful one. The old command was a bare Add-WindowsCapability, and
# powershell.exe exits 0 when a command inside it writes a non-terminating
# error — which is exactly what a name Windows does not recognise
# produces. So "0" meant the shell had started, not that anything had been
# installed, and every failure on a machine was reported as a success.
#
# -ErrorAction Stop turns those into terminating errors the catch can see,
# and the state is read back afterwards rather than assumed: Windows can
# accept the command and still not have the pack on when it returns.
#
# dism.exe rather than Add-WindowsCapability, for one reason: it prints a
# percentage and the cmdlet does not. Add-WindowsCapability reports through
# PowerShell's progress stream, which is the one stream that cannot be
# redirected, so a hidden elevated shell throws it away — which is why this
# could only ever offer a clock. Both drive the same servicing engine.
#
# The redirect goes through cmd so that DISM writes into the file as it
# goes. PowerShell's own > buffers, and a progress file that arrives all at
# once at the end is not progress.
SCRIPT = (
    '$n = "%s"; $log = "%s"; '
    'try { $c = Get-WindowsCapability -Online -Name $n -ErrorAction Stop } '
    'catch { exit 13 } '
    'if ($c -eq $null) { exit 13 } '
    'if ($c.State -eq "Installed") { exit 10 } '
    '& cmd.exe /c "dism.exe /online /Add-Capability '
    '/CapabilityName:$n /NoRestart > ""$log"" 2>&1"; '
    '$code = $LASTEXITCODE; '
    '$c = Get-WindowsCapability -Online -Name $n; '
    'if ($c.State -eq "Installed") { exit 0 } '
    'if ($code -ne 0) { exit 12 } '
    'exit 11'
)

# DISM draws its bar by rewriting one line with backspaces, so a redirected
# file is one long smear with every percentage it has passed through still
# in it. The last one is the current one.
PERCENT = re.compile(r"(\d{1,3})(?:[.,]\d+)?%")


def log_path():
    """Where the elevated process writes what DISM is saying.

    Somewhere both processes can reach: the elevated one runs as the same
    user, so the user's own temp directory is the same directory.
    """
    import tempfile
    return os.path.join(tempfile.gettempdir(), "squint-langpack.log")


def progress(path=None):
    """How far along, 0-100, or None if nothing has been said yet.

    None is a real answer and not a failure — DISM says nothing for the
    first stretch while it works out what it is doing, and the caller
    falls back to the elapsed clock rather than drawing an empty bar and
    calling it 0%.
    """
    path = log_path() if path is None else path
    try:
        with open(path, "r", errors="ignore") as handle:
            text = handle.read()
    except Exception:
        return None
    found = PERCENT.findall(text.replace("\b", ""))
    if not found:
        return None
    try:
        return max(0, min(100, int(found[-1])))
    except ValueError:
        return None


def _encoded(command):
    """PowerShell's own way of passing a command without quoting it.

    The command has to survive being an element of an -ArgumentList inside
    another PowerShell command, and quoting it through two shells by hand
    is the sort of thing that works until a name contains a character
    nobody thought about. -EncodedCommand is base64 of UTF-16, which has
    no characters that mean anything to either shell.
    """
    import base64
    return base64.b64encode(command.encode("utf-16-le")).decode("ascii")


def install(capability, timeout=INSTALL_TIMEOUT):
    """Ask Windows to add the pack. (ok, message).

    Elevation goes through Start-Process -Verb RunAs, which is the same
    consent dialog any installer produces. A user who declines gets a
    plain sentence rather than an error, because declining is a reasonable
    thing to do and not a fault.
    """
    if not supported():
        return False, "Language packs are a Windows thing."
    if not CAPABILITY.match(str(capability)):
        # Whatever is passed here ends up inside a PowerShell command, so
        # it is checked against the shape Windows uses rather than trusted.
        return False, "That is not a Windows OCR capability name."
    where = log_path()
    try:
        # Left behind by the last install, and a stale file would show a
        # bar sitting at 100% before this one has started.
        if os.path.exists(where):
            os.remove(where)
    except Exception:
        pass
    try:
        done = _run([
            "$p = Start-Process powershell -Verb RunAs -Wait -PassThru "
            "-WindowStyle Hidden -ArgumentList "
            "'-NoProfile','-EncodedCommand','%s'; $p.ExitCode"
            % _encoded(SCRIPT % (capability, where))], timeout)
    except subprocess.TimeoutExpired:
        return False, ("Windows is still working on it. It carries on in "
                       "the background — check Settings › Engines again in "
                       "a few minutes.")
    except Exception as exc:
        return False, "Could not ask Windows: %s" % exc

    output = ((done.stdout or "") + (done.stderr or "")).strip()
    low = output.lower()
    if "canceled" in low or "cancelled" in low or "denied" in low:
        return False, ("Windows was not given permission, so nothing was "
                       "installed. " + NEEDS_ADMIN)
    tail = output.splitlines()[-1].strip() if output else ""
    try:
        code = int(tail)
    except ValueError:
        code = None
    return _message_for_code(code, output)


def _message_for_code(code, output):
    """The one exit code from install(), or one pack's line from the
    results file install_many() writes — same six outcomes either way,
    so both go through the same sentences.
    """
    if code == DONE:
        return True, "Installed."
    if code == ALREADY:
        return True, "Windows already had this one."
    if code == NO_SUCH_PACK:
        return False, ("This edition of Windows does not offer that pack. "
                       "A Gemini or Google key reads any language without "
                       "one.")
    if code == FAILED:
        return False, ("Windows could not install it. That is usually the "
                       "download rather than the pack — check the "
                       "connection and try again. A Gemini or Google key "
                       "reads any language meanwhile.")
    if code == NOT_CONFIRMED:
        return False, ("Windows accepted it but the pack is still not "
                       "there. It sometimes finishes in the background — "
                       "open this panel again in a few minutes.")
    # No number came back at all. Something stopped the elevated shell
    # before the script ran, and saying "installed" here is the mistake
    # this whole change exists to remove.
    return False, ("Windows did not say whether it worked: %s"
                   % (output[-160:] or "no output"))


def results_path():
    """Where install_many()'s elevated shell writes one verdict per pack.

    The exit code channel that install() uses is one integer for the
    whole elevated process, which is enough for one pack. A batch needs
    several independent verdicts back — three installed and a fourth
    this edition does not offer is not the same outcome as any one of
    those alone — so this is a second file, alongside the progress log,
    that the elevated shell writes to only once, at the very end.
    """
    import tempfile
    return os.path.join(tempfile.gettempdir(), "squint-langpack-results.txt")


# Builds ONE dism.exe call carrying every capability that still needs
# installing, which is what puts them in a single servicing session —
# confirmed by hand: two packs together took barely longer than one
# alone, nothing like twice as long, because the fixed cost (the servicing
# lock, the session, the final commit) is paid once rather than per pack.
# Calling install() several times would ask permission once per language
# instead.
#
# Already-installed packs are filtered out first and never touch dism —
# re-running setup should not re-download what a machine already has, and
# a capability this edition simply does not offer is told apart from one
# that failed to install, the same distinction install() makes.
SCRIPT_MANY = (
    '$names = @(%s); $log = "%s"; $resultsPath = "%s"; '
    '$toInstall = New-Object System.Collections.ArrayList; '
    '$out = New-Object System.Collections.ArrayList; '
    'foreach ($n in $names) { '
    '  try { $c = Get-WindowsCapability -Online -Name $n -ErrorAction Stop } '
    '  catch { [void]$out.Add("$n|13"); continue } '
    '  if ($c -eq $null) { [void]$out.Add("$n|13"); continue } '
    '  if ($c.State -eq "Installed") { [void]$out.Add("$n|10"); continue } '
    '  [void]$toInstall.Add($n) '
    '} '
    'if ($toInstall.Count -gt 0) { '
    '  $capArgs = ($toInstall | ForEach-Object { "/CapabilityName:$_" }) '
    '    -join " "; '
    '  & cmd.exe /c "dism.exe /online /Add-Capability $capArgs /NoRestart '
    '> ""$log"" 2>&1"; '
    '  $code = $LASTEXITCODE; '
    '  foreach ($n in $toInstall) { '
    '    $c = Get-WindowsCapability -Online -Name $n; '
    '    if ($c.State -eq "Installed") { [void]$out.Add("$n|0") } '
    '    elseif ($code -ne 0) { [void]$out.Add("$n|12") } '
    '    else { [void]$out.Add("$n|11") } '
    '  } '
    '} '
    '($out -join "`n") | Out-File -FilePath $resultsPath -Encoding utf8; '
    'exit 0'
)


def _read_results(path):
    """{capability: code}, from install_many()'s results file. Missing or
    unreadable is an empty dict, not an error — the caller already knows
    to treat a capability with no entry as "nothing is known"."""
    out = {}
    try:
        with open(path, "r", errors="ignore") as handle:
            for line in handle:
                name, sep, code = line.strip().partition("|")
                if not sep:
                    continue
                try:
                    out[name] = int(code)
                except ValueError:
                    pass
    except Exception:
        pass
    return out


def install_many(capabilities, timeout=INSTALL_TIMEOUT):
    """Install several packs behind one admin prompt. {capability: (ok, message)}.

    A dict rather than install()'s single (ok, message): a batch can
    partly succeed, and three packs installed plus a fourth this Windows
    edition does not offer is worth reporting as exactly that, not
    flattened into one verdict for the whole request.
    """
    capabilities = list(dict.fromkeys(str(c) for c in capabilities))
    if not supported():
        return {c: (False, "Language packs are a Windows thing.")
                for c in capabilities}
    bad = [c for c in capabilities if not CAPABILITY.match(c)]
    if bad:
        return {c: (False, "That is not a Windows OCR capability name.")
                for c in capabilities}
    if not capabilities:
        return {}

    log, results = log_path(), results_path()
    for path in (log, results):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    names = ", ".join("'%s'" % c for c in capabilities)
    script = SCRIPT_MANY % (names, log, results)
    try:
        done = _run([
            "$p = Start-Process powershell -Verb RunAs -Wait -PassThru "
            "-WindowStyle Hidden -ArgumentList "
            "'-NoProfile','-EncodedCommand','%s'; $p.ExitCode"
            % _encoded(script)], timeout)
    except subprocess.TimeoutExpired:
        return {c: (False, "Windows is still working on it. It carries on "
                    "in the background — check Settings › Engines again in "
                    "a few minutes.") for c in capabilities}
    except Exception as exc:
        return {c: (False, "Could not ask Windows: %s" % exc)
                for c in capabilities}

    output = ((done.stdout or "") + (done.stderr or "")).strip()
    low = output.lower()
    if "canceled" in low or "cancelled" in low or "denied" in low:
        return {c: (False, "Windows was not given permission, so nothing "
                    "was installed. " + NEEDS_ADMIN) for c in capabilities}

    codes = _read_results(results)
    return {c: _message_for_code(codes.get(c), output) for c in capabilities}
