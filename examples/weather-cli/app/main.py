import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("AGENTHUB_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("AGENTHUB_API_KEY", "")


def llm(messages, model="deepseek-chat"):
    if not BASE_URL or not API_KEY:
        return None
    payload = json.dumps({"model": model, "messages": messages}).encode()
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print("[weather-cli] LLM call failed: %s" % e, file=sys.stderr)
        return None


def extract_city(question):
    if BASE_URL and API_KEY:
        reply = llm([
            {
                "role": "system",
                "content": "你是城市提取器。从用户问题中提取查询天气的城市，只输出城市名，不要输出任何其他内容。提取不到就输出 NONE。",
            },
            {"role": "user", "content": question},
        ])
        if reply:
            city = reply.strip().strip("\"'。.，").splitlines()[0].strip()
            if city and city.upper() != "NONE":
                return city
    m = re.search(r"([\u4e00-\u9fa5]{2,4}?)(?:今天|明天|后天|现在|天气|下雨|下雪|气温)", question)
    if m:
        return m.group(1)
    return "Beijing"


def fetch_weather(city):
    url = "https://wttr.in/%s?format=3" % urllib.parse.quote(city)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode().strip()


def main():
    question = " ".join(sys.argv[1:]) or "上海今天天气怎么样"
    city = extract_city(question)
    print("[weather-cli] city: %s" % city)
    try:
        raw = fetch_weather(city)
    except Exception as e:
        print("[weather-cli] weather query failed: %s" % e, file=sys.stderr)
        return 1
    if BASE_URL and API_KEY:
        answer = llm([
            {"role": "system", "content": "你是天气助手。把原始天气数据组织成一句自然的中文回答。"},
            {"role": "user", "content": "问题：%s\n城市：%s\n原始数据：%s" % (question, city, raw)},
        ])
        if answer:
            print(answer)
            return 0
    print(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
