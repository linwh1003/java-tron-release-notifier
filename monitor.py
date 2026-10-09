
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "tronprotocol/java-tron"
BASELINE_VERSION = "4.8.2.3"
STATE_FILE = Path("state/last_notified_version.txt")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def get_json(url, headers=None, data=None):
    req_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "java-tron-release-monitor",
    }
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(
        url, headers=req_headers, data=data
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_version(tag):
    match = re.search(r"(\d+(?:\.\d+)+)$", tag.strip())
    if not match:
        return None
    return tuple(int(x) for x in match.group(1).split("."))


def compare_versions(a, b):
    size = max(len(a), len(b))
    a = a + (0,) * (size - len(a))
    b = b + (0,) * (size - len(b))
    return (a > b) - (a < b)


def get_latest_release():
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    releases = []
    for page in range(1, 6):
        query = urllib.parse.urlencode({
            "per_page": 100,
            "page": page
        })
        data = get_json(
            f"https://api.github.com/repos/{REPO}/releases?{query}",
            headers=headers
        )
        if not data:
            break
        releases.extend(data)
        if len(data) < 100:
            break

    stable = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue

        version = parse_version(release.get("tag_name", ""))
        if version is not None:
            stable.append((version, release))

    if not stable:
        raise RuntimeError("没有找到可识别的正式 Release")

    return max(stable, key=lambda x: x[0])


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "请检查 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID Secrets"
        )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }).encode("utf-8")

    result = get_json(
        url,
        headers={"Content-Type": "application/json"},
        data=body
    )

    if not result.get("ok"):
        raise RuntimeError("Telegram 消息发送失败")


def main():
    version, release = get_latest_release()
    tag = release["tag_name"]
    version_text = ".".join(map(str, version))

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if STATE_FILE.exists():
        previous_tag = STATE_FILE.read_text(
            encoding="utf-8"
        ).strip()
        previous_version = parse_version(previous_tag)
        if previous_version is None:
            raise RuntimeError("版本状态文件内容无效")
    else:
        previous_tag = BASELINE_VERSION
        previous_version = parse_version(BASELINE_VERSION)

    if compare_versions(version, previous_version) <= 0:
        print(
            f"无需通知。最新版本：{version_text}；"
            f"已记录版本：{previous_tag}"
        )
        return

    published = release.get("published_at") or "未知"
    link = release.get("html_url") or (
        f"https://github.com/{REPO}/releases"
    )

    message = (
        "🚀 java-tron 发布了新正式版本！\n\n"
        f"之前版本：{previous_tag}\n"
        f"最新版本：{version_text}\n"
        f"发布时间：{published}\n\n"
        f"查看详情：{link}"
    )

    send_telegram(message)

    # 只有发送成功后才更新状态
    STATE_FILE.write_text(tag + "\n", encoding="utf-8")
    print(f"Telegram 通知发送成功：{tag}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"监控失败：{exc}", file=sys.stderr)
        sys.exit(1)
