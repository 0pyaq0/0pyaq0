#!/usr/bin/env python3
"""neofetch 스타일 GitHub 프로필 README 생성기.

dark_mode.svg / light_mode.svg 두 장을 만들고, README.md는 GitHub 테마에 맞춰
둘 중 하나를 보여 줍니다. 표준 라이브러리만 사용하며,
GITHUB_TOKEN 환경변수가 있으면 인증해서 호출합니다.
사용법: python3 gen_readme.py
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

USERNAME = "0pyaq0"

# ─── 여기의 [ ] 값을 직접 채워 주세요 ───────────────────────────
# ("항목", "값") 순서대로 출력됩니다. 항목이 None이면 ". " 빈 줄입니다.
INFO = [
    ("OS", "[OS]"),
    ("Uptime", "[Uptime]"),
    ("Host", "한국폴리텍대학 서울강서캠퍼스"),
    ("Kernel", "빅데이터소프트웨어과"),
    ("IDE", "[IDE]"),
    (None, None),
    ("Languages.Programming", "[Programming languages]"),
    ("Languages.Computer", "[Computer languages]"),
    ("Languages.Real", "한국어"),
    (None, None),
    ("Hobbies.Software", "[Software hobbies]"),
    ("Hobbies.Hardware", "[Hardware hobbies]"),
]

CONTACT = [
    ("Email.Personal", "[Personal email]"),
    ("LinkedIn", "[LinkedIn]"),
    ("Discord", "[Discord]"),
]

# 왼쪽에 넣을 ASCII 아트 파일 (없으면 정보 패널만 그립니다)
# 다크 모드 기준(밝은 부분일수록 진한 글자)으로 저장하고, 라이트 모드에서는 자동으로 반전합니다.
ASCII_ART_FILE = "ascii_art.txt"
ART_RAMP = ".:-=+*#%@"
# ────────────────────────────────────────────────────────────────

COLS = 60          # 정보 패널 한 줄 폭 (영문 기준 칸 수)
FONT_SIZE = 16
CHAR_W = 9.6       # 16px 고정폭 글꼴의 영문 글자 폭 (0.6em)
LINE_H = 30
PAD = 30
ART_FONT_SIZE = 12  # ASCII 아트는 더 작은 글자로 촘촘하게 그립니다
ART_CHAR_W = ART_FONT_SIZE * 0.6
ART_LINE_H = 14
# 한글은 대부분의 글꼴에서 약 1em(=16px) 폭이라 영문 칸으로 환산하면 약 1.67칸입니다.
# 각 줄은 textLength로 패널 폭에 정확히 맞춰 그리므로, 글꼴이 달라도 오른쪽 끝이 맞습니다.
WIDE_CHAR_COLS = FONT_SIZE / CHAR_W

THEMES = {
    "dark": {"bg": "#161b22", "text": "#c9d1d9", "key": "#ae75da", "value": "#a5d6ff",
             "cc": "#616e7f", "add": "#3fb950", "del": "#f85149"},
    "light": {"bg": "#f6f8fa", "text": "#24292f", "key": "#953800", "value": "#0a3069",
              "cc": "#c2cfde", "add": "#1a7f37", "del": "#cf222e"},
}

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN")
ROOT = os.path.dirname(os.path.abspath(__file__))


class RateLimited(Exception):
    pass


class ApiError(Exception):
    pass


def request(path):
    """GitHub API를 호출해 (상태코드, JSON) 을 돌려줍니다."""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USERNAME}-readme-generator")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        remaining = e.headers.get("X-RateLimit-Remaining")
        if e.code == 429 or (e.code == 403 and (remaining == "0" or "rate limit" in body.lower())):
            raise RateLimited(e.headers.get("X-RateLimit-Reset"))
        raise ApiError(f"{e.code} {url}: {body[:200]}")
    except urllib.error.URLError as e:
        raise ApiError(f"{url}: {e.reason}")


def get_repos():
    repos, page = [], 1
    while True:
        _, data = request(f"/users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repos.extend(data)
        if len(data) < 100:
            return repos
        page += 1


def contributor_lines(repo_full_name, retries=8):
    """레포의 /stats/contributors에서 내 (additions, deletions). 계산 중(202)이면 재시도."""
    for attempt in range(retries):
        try:
            status, data = request(f"/repos/{repo_full_name}/stats/contributors")
        except ApiError as e:  # 차단된 레포 등 한 레포 오류로 전체를 멈추지 않음
            print(f"경고: {repo_full_name} 통계를 가져오지 못해 Lines of Code에서 제외했습니다 ({e}).",
                  file=sys.stderr)
            return 0, 0
        if status == 202:
            time.sleep(min(2 ** attempt, 30))
            continue
        if status == 204 or not data:  # 빈 레포
            return 0, 0
        for c in data:
            if c.get("author") and c["author"]["login"].lower() == USERNAME.lower():
                return sum(w["a"] for w in c["weeks"]), sum(w["d"] for w in c["weeks"])
        return 0, 0
    print(f"경고: {repo_full_name} 통계가 아직 준비되지 않아 Lines of Code에서 제외했습니다.", file=sys.stderr)
    return 0, 0


def get_stats():
    _, user = request(f"/users/{USERNAME}")
    repos = get_repos()
    _, search = request(f"/search/commits?q=author:{USERNAME}&per_page=1")
    adds = dels = 0
    for r in repos:
        a, d = contributor_lines(r["full_name"])
        adds, dels = adds + a, dels + d
    return {
        "repos": user["public_repos"],
        "stars": sum(r["stargazers_count"] for r in repos if not r["fork"]),
        "commits": search["total_count"],
        "followers": user["followers"],
        "loc": adds - dels,
        "add": adds,
        "del": dels,
    }


# ─── SVG 그리기 ─────────────────────────────────────────────────

def cols(text):
    return sum(WIDE_CHAR_COLS if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def span(cls, text):
    return f'<tspan class="{cls}">{escape(text)}</tspan>'


def key_spans(key):
    """'Languages.Real' → 'Languages' . 'Real' 처럼 점은 기본색, 단어는 key 색."""
    return ".".join(span("key", part) for part in key.split("."))


def dots(n):
    return span("cc", " " + "." * max(int(n), 1) + " ")


class Panel:
    def __init__(self, x):
        self.x, self.right, self.y, self.out = x, x + COLS * CHAR_W, PAD + 20, []

    def text(self, inner, fit=True):
        """한 줄을 그립니다. fit이면 textLength로 패널 폭에 딱 맞춥니다."""
        fit_attr = f' textLength="{COLS * CHAR_W:.1f}" lengthAdjust="spacing"' if fit else ""
        self.out.append(f'<text x="{self.x:.1f}" y="{self.y}"{fit_attr}>{inner}</text>')

    def newline(self):
        self.y += LINE_H

    def rule(self, title):
        self.text(escape(title) + " " + span("cc", "─" * (COLS - len(title) - 1)))
        self.newline()

    def item(self, key, value):
        if key is None:
            self.text(span("cc", ". "), fit=False)
        else:
            left = f". {key}:"
            n = round(COLS - len(left) - cols(value) - 2)
            self.text(span("cc", ". ") + key_spans(key) + ":" + dots(n) + span("value", value))
        self.newline()

    def pair(self, k1, v1, k2, v2):
        """'. Repos: .... 54 | Stars: .... 4' 처럼 한 줄에 두 항목 (모두 영문이라 칸 계산이 정확)."""
        half = COLS // 2
        n1 = half - len(f". {k1}:") - len(v1) - 3
        n2 = COLS - half - len(f"| {k2}:") - len(v2) - 2
        self.text(span("cc", ". ") + key_spans(k1) + ":" + dots(n1) + span("value", v1) + " | "
                  + key_spans(k2) + ":" + dots(n2) + span("value", v2))
        self.newline()

    def loc(self, s):
        total, add, dele = f"{s['loc']:,}", f"{s['add']:,}", f"{s['del']:,}"
        tail_len = len(f"{total} ( {add}++, {dele}-- )")
        key = "Lines of Code on GitHub"
        n = COLS - len(f". {key}:") - tail_len - 2
        self.text(span("cc", ". ") + key_spans(key) + ":" + dots(n) + span("value", total) + " ( "
                  + span("add", add + "++") + ", " + span("del", dele + "--") + " )")
        self.newline()


def read_ascii_art():
    path = os.path.join(ROOT, ASCII_ART_FILE)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().rstrip("\n").split("\n")


def invert_art(lines):
    table = str.maketrans(ART_RAMP, ART_RAMP[::-1])
    return [line.translate(table) for line in lines]


def render_svg(stats, theme):
    c = THEMES[theme]
    art = read_ascii_art()
    if theme == "light":
        art = invert_art(art)
    art_w = (max(map(len, art)) * ART_CHAR_W + PAD) if art else 0

    p = Panel(PAD + art_w)
    p.rule(f"{USERNAME}@github")
    for k, v in INFO:
        p.item(k, v)
    p.rule("- Contact")
    for k, v in CONTACT:
        p.item(k, v)
    p.rule("- GitHub Stats")
    p.pair("Repos", f"{stats['repos']:,}", "Stars", f"{stats['stars']:,}")
    p.pair("Commits", f"{stats['commits']:,}", "Followers", f"{stats['followers']:,}")
    p.loc(stats)
    p.text(span("cc", "─" * COLS))

    width = round(p.right + PAD)
    height = max(p.y + PAD, PAD * 2 + len(art) * ART_LINE_H)
    art_top = (height - len(art) * ART_LINE_H) / 2 + ART_FONT_SIZE
    art_svg = "\n".join(
        f'<text x="{PAD}" y="{art_top + i * ART_LINE_H:.1f}" font-size="{ART_FONT_SIZE}px">{escape(line)}</text>'
        for i, line in enumerate(art))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono',monospace" font-size="{FONT_SIZE}px">
<style>
@font-face {{ src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; size-adjust: 109%; }}
text, tspan {{ white-space: pre; }}
text {{ fill: {c['text']}; }}
.key {{ fill: {c['key']}; }}
.value {{ fill: {c['value']}; }}
.cc {{ fill: {c['cc']}; }}
.add {{ fill: {c['add']}; }}
.del {{ fill: {c['del']}; }}
</style>
<rect width="{width}px" height="{height}px" fill="{c['bg']}" rx="15"/>
{art_svg}
{chr(10).join(p.out)}
</svg>
"""


README = f"""<p align="center">
  <a href="https://github.com/{USERNAME}">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="dark_mode.svg">
      <img alt="{USERNAME}'s GitHub Profile README" src="light_mode.svg">
    </picture>
  </a>
</p>
"""


def write(name, content):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        f.write(content)


def main():
    try:
        stats = get_stats()
    except RateLimited as e:
        reset = ""
        if e.args and e.args[0]:
            reset = time.strftime(" (초기화 시각: %Y-%m-%d %H:%M:%S)", time.localtime(int(e.args[0])))
        print(f"GitHub API 호출 한도를 초과했습니다{reset}. 잠시 후 다시 실행하거나 "
              "GITHUB_TOKEN 환경변수를 설정해 주세요. 파일은 변경하지 않았습니다.", file=sys.stderr)
        sys.exit(1)
    except ApiError as e:
        print(f"GitHub API 호출에 실패했습니다: {e}\n파일은 변경하지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    for theme in THEMES:
        write(f"{theme}_mode.svg", render_svg(stats, theme))
    write("README.md", README)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
