#!/usr/bin/env python3
"""neofetch 스타일 GitHub 프로필 README.md 생성기.

표준 라이브러리만 사용합니다. GITHUB_TOKEN 환경변수가 있으면 인증해서 호출합니다.
사용법: python3 gen_readme.py
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request

USERNAME = "0pyaq0"
WIDTH = 64  # 한 줄 전체 폭 (한글 등 넓은 문자는 2칸)

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
# ────────────────────────────────────────────────────────────────

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN")


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
    """레포의 /stats/contributors에서 내 additions - deletions. 계산 중(202)이면 재시도."""
    for attempt in range(retries):
        status, data = request(f"/repos/{repo_full_name}/stats/contributors")
        if status == 202:
            time.sleep(min(2 ** attempt, 30))
            continue
        if status == 204 or not data:  # 빈 레포
            return 0
        total = 0
        for c in data:
            if c.get("author") and c["author"]["login"].lower() == USERNAME.lower():
                total += sum(w["a"] - w["d"] for w in c["weeks"])
        return total
    print(f"경고: {repo_full_name} 통계가 아직 준비되지 않아 Lines of Code에서 제외했습니다.", file=sys.stderr)
    return 0


def get_stats():
    _, user = request(f"/users/{USERNAME}")
    repos = get_repos()
    stars = sum(r["stargazers_count"] for r in repos if not r["fork"])
    _, search = request(f"/search/commits?q=author:{USERNAME}&per_page=1")
    loc = sum(contributor_lines(r["full_name"]) for r in repos)
    return [
        ("Repos", f"{user['public_repos']:,}"),
        ("Commits", f"{search['total_count']:,}"),
        ("Stars", f"{stars:,}"),
        ("Followers", f"{user['followers']:,}"),
        ("Lines of Code on GitHub", f"{loc:,}"),
    ]


def width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def line(key, value):
    if key is None:
        return ". "
    left, right = f". {key}: ", f" {value}"
    dots = WIDTH - width(left) - width(right)
    return left + "." * max(dots, 1) + right


def rule(title):
    return title + " " + "─" * (WIDTH - width(title) - 1)


def render(stats):
    out = [rule(f"{USERNAME}@github")]
    out += [line(k, v) for k, v in INFO]
    out += ["", rule("- Contact")]
    out += [line(k, v) for k, v in CONTACT]
    out += ["", rule("- GitHub Stats")]
    out += [line(k, v) for k, v in stats]
    return "```text\n" + "\n".join(out) + "\n```\n"


def main():
    try:
        stats = get_stats()
    except RateLimited as e:
        reset = ""
        if e.args and e.args[0]:
            reset = time.strftime(" (초기화 시각: %Y-%m-%d %H:%M:%S)", time.localtime(int(e.args[0])))
        print(f"GitHub API 호출 한도를 초과했습니다{reset}. 잠시 후 다시 실행하거나 "
              "GITHUB_TOKEN 환경변수를 설정해 주세요. README.md는 변경하지 않았습니다.", file=sys.stderr)
        sys.exit(1)
    except ApiError as e:
        print(f"GitHub API 호출에 실패했습니다: {e}\nREADME.md는 변경하지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    readme = render(stats)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(readme)
    print(readme)


if __name__ == "__main__":
    main()
