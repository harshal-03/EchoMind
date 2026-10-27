"""extras.py - read-only email digest + GitHub summary for EchoMind.

Self-contained. Off by default. Data only flows IN (headers / repo stats);
nothing from notes, audio or reasoning is ever sent out.
Env vars:
  ECHOMIND_MAIL=1  ECHOMIND_IMAP_HOST (imap.gmail.com)  ECHOMIND_MAIL_USER  ECHOMIND_MAIL_PASS
  ECHOMIND_GITHUB=1  ECHOMIND_GITHUB_USER  ECHOMIND_GITHUB_TOKEN (read-only)
"""
import difflib
import email
import imaplib
import json
import os
import re
import urllib.error
import urllib.request
from email.header import decode_header, make_header
from email.utils import parseaddr

ENABLE_MAIL = os.environ.get("ECHOMIND_MAIL", "0") == "1"
ENABLE_GITHUB = os.environ.get("ECHOMIND_GITHUB", "0") == "1"
MAIL_HOST = os.environ.get("ECHOMIND_IMAP_HOST", "imap.gmail.com")
MAIL_USER = os.environ.get("ECHOMIND_MAIL_USER", "")
MAIL_PASS = os.environ.get("ECHOMIND_MAIL_PASS", "")
GH_USER = os.environ.get("ECHOMIND_GITHUB_USER", "")
GH_TOKEN = os.environ.get("ECHOMIND_GITHUB_TOKEN", "")
GH_HOST = "api.github.com"
EXTRA_HOSTS = (GH_HOST, MAIL_HOST)  # add these to ONLINE_ALLOWLIST


class ExtrasError(Exception):
    pass


def _log(host, what):
    """Record the call in netlog. Signature of netlog.record is unverified."""
    try:
        import netlog
        try:
            netlog.record(host, what)
        except TypeError:
            netlog.record(host)
    except Exception:
        pass


# ---------------------------------------------------------------- email
def _dec(v):
    try:
        return str(make_header(decode_header(v or ""))).strip()
    except Exception:
        return (v or "").strip()


def unread_emails(limit=5):
    """Return (total_unread, [{'from','subject','date'}...]) newest first.
    Read-only: mailbox opened readonly and BODY.PEEK, so nothing is marked read."""
    if not ENABLE_MAIL:
        raise ExtrasError("Email is switched off. Set ECHOMIND_MAIL=1.")
    if not (MAIL_USER and MAIL_PASS):
        raise ExtrasError("Email login is not set.")
    _log(MAIL_HOST, "imap unread headers")
    m = None
    try:
        m = imaplib.IMAP4_SSL(MAIL_HOST, timeout=15)
        m.login(MAIL_USER, MAIL_PASS)
        m.select("INBOX", readonly=True)
        _, data = m.search(None, "UNSEEN")
        ids = data[0].split()
        items = []
        for i in reversed(ids[-limit:]):
            _, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            msg = email.message_from_bytes(d[0][1])
            name, addr = parseaddr(_dec(msg.get("From")))
            items.append({"from": name or addr or "unknown",
                          "subject": _dec(msg.get("Subject")) or "no subject",
                          "date": _dec(msg.get("Date"))})
        return len(ids), items
    except imaplib.IMAP4.error:
        raise ExtrasError("The mail server rejected the login.")
    except OSError:
        raise ExtrasError("I could not reach the mail server.")
    finally:
        try:
            if m:
                m.logout()
        except Exception:
            pass


def mail_digest(limit=5):
    total, items = unread_emails(limit)
    if total == 0:
        return "You have no unread emails."
    parts = ["%s from %s" % (x["subject"], x["from"]) for x in items]
    head = "You have %d unread email%s." % (total, "" if total == 1 else "s")
    more = " Showing the latest %d." % len(items) if total > len(items) else ""
    return head + more + " " + "; ".join(parts) + "."


# --------------------------------------------------------------- github
def _gh(path):
    if not ENABLE_GITHUB:
        raise ExtrasError("GitHub is switched off. Set ECHOMIND_GITHUB=1.")
    if not GH_USER:
        raise ExtrasError("GitHub user is not set.")
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "EchoMind-Pi"}
    if GH_TOKEN:
        headers["Authorization"] = "Bearer " + GH_TOKEN
    _log(GH_HOST, "github api read")
    req = urllib.request.Request("https://" + GH_HOST + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()), r.headers
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ExtrasError("GitHub rejected the token.")
        if e.code in (403, 429):
            raise ExtrasError("GitHub rate limit reached. Try again later.")
        if e.code == 409:
            return [], {}
        if e.code == 404:
            raise ExtrasError("GitHub could not find that.")
        raise ExtrasError("GitHub error %d." % e.code)
    except OSError:
        raise ExtrasError("I could not reach GitHub.")


def _count(path):
    """Count items of a list endpoint with one call (per_page=1 + Link header)."""
    sep = "&" if "?" in path else "?"
    body, hdr = _gh(path + sep + "per_page=1")
    link = hdr.get("Link", "") if hdr else ""
    m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
    return int(m.group(1)) if m else len(body)


def list_repos():
    if GH_TOKEN:
        path = "/user/repos?per_page=100&sort=pushed&affiliation=owner"
    else:
        path = "/users/%s/repos?per_page=100&sort=pushed" % GH_USER
    body, _ = _gh(path)
    return body


def github_overview(limit=5):
    repos = list_repos()
    if not repos:
        return "I found no repositories."
    top = ["%s%s" % (r["name"], " in " + r["language"] if r.get("language") else "")
           for r in repos[:limit]]
    return ("You have %d repositories. Most recently updated: %s."
            % (len(repos), ", ".join(top)))


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_repo(text, repos):
    """Match a spoken repo name ('echo mind') against real repo names."""
    t = _norm(text)
    hits = [r for r in repos if len(_norm(r["name"])) >= 3 and _norm(r["name"]) in t]
    if hits:
        return max(hits, key=lambda r: len(_norm(r["name"])))
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = words + [a + b for a, b in zip(words, words[1:])]
    best, score = None, 0.8
    for r in repos:
        for g in grams:
            s = difflib.SequenceMatcher(None, _norm(r["name"]), g).ratio()
            if s > score:
                best, score = r, s
    return best


def repo_stats(text):
    repos = list_repos()
    r = find_repo(text, repos)
    if not r:
        names = ", ".join(x["name"] for x in repos[:5])
        return "I could not tell which repository you mean. Try: " + names + "."
    full = r["full_name"]
    commits = _count("/repos/%s/commits" % full)
    prs = _count("/repos/%s/pulls?state=open" % full)
    issues = max(r.get("open_issues_count", 0) - prs, 0)
    return ("%s has %d commits, %d open pull request%s waiting to merge, and %d open issue%s."
            % (r["name"], commits, prs, "" if prs == 1 else "s",
               issues, "" if issues == 1 else "s"))


# -------------------------------------------------------------- routing
_MAIL = re.compile(r"\b(unread|new|latest)\b.*\b(e-?mails?|mail|inbox|messages)\b"
                   r"|\b(check|read|summari[sz]e)\b.*\b(e-?mails?|inbox)\b", re.I)
_GH = re.compile(r"\bgit ?hub\b|\brepos?\b|\brepositor(y|ies)\b", re.I)
_STAT = re.compile(r"\b(commits?|pull requests?|prs?|pending|merge|issues?)\b", re.I)


def route_extra(text):
    """Return ('mail_digest'|'github_overview'|'github_repo', args) or None."""
    if _MAIL.search(text):
        return ("mail_digest", {})
    if _STAT.search(text) and (_GH.search(text) or re.search(r"\b(in|of|for|on)\b", text, re.I)):
        if ENABLE_GITHUB:
            return ("github_repo", {"query": text})
    if _GH.search(text):
        return ("github_overview", {})
    return None


def run_extra(tool, args, online):
    """Execute a routed tool. `online` is the orchestrator's online-switch state."""
    if not online:
        return "Turn the online switch on first, then ask me again."
    try:
        if tool == "mail_digest":
            return mail_digest()
        if tool == "github_overview":
            return github_overview()
        if tool == "github_repo":
            return repo_stats(args.get("query", ""))
    except ExtrasError as e:
        return str(e)
    return "I do not know that request."


if __name__ == "__main__":
    import sys
    cmd = " ".join(sys.argv[1:]) or "unread emails"
    r = route_extra(cmd)
    print("route:", r)
    print(run_extra(r[0], r[1], True) if r else "no match")
