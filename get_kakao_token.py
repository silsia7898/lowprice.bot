#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_kakao_token.py
카카오 인가 코드를 이용하여 액세스 토큰 및 리프레시 토큰을 발급받고
.env 파일에 KAKAO_REFRESH_TOKEN 항목을 자동으로 업데이트합니다.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
REDIRECT_URI = "http://localhost"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def load_env(path: Path) -> dict:
    env_vars = {}
    if not path.exists():
        return env_vars
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def save_env_var(path: Path, key: str, value: str) -> None:
    lines = []
    found = False
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def request_token(auth_code: str, redirect_uri: str = REDIRECT_URI):
    env_vars = load_env(ENV_PATH)
    client_id = env_vars.get("KAKAO_REST_API_KEY")
    client_secret = env_vars.get("KAKAO_CLIENT_SECRET")

    if not client_id:
        print("❌ [.env 오류] KAKAO_REST_API_KEY 항목이 없습니다.", file=sys.stderr)
        sys.exit(1)

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": auth_code
    }
    if client_secret:
        data["client_secret"] = client_secret

    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            refresh_token = res_json.get("refresh_token")
            access_token = res_json.get("access_token")

            if not refresh_token:
                print(f"⚠️ 리프레시 토큰이 응답에 없습니다: {res_json}", file=sys.stderr)
                return False

            save_env_var(ENV_PATH, "KAKAO_REFRESH_TOKEN", refresh_token)
            if access_token:
                save_env_var(ENV_PATH, "KAKAO_ACCESS_TOKEN", access_token)

            print("✅ 카카오 토큰 발급 완료!")
            print(f"🔑 리프레시 토큰: {refresh_token[:10]}... (저장 완료)")
            return True

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"❌ 카카오 토큰 발급 실패 (HTTP {e.code})", file=sys.stderr)
        print(f"상세 내용: {err_msg}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ 요청 중 오류 발생: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        code = sys.argv[1]
    else:
        code = input("카카오 인가 코드를 입력하세요: ").strip()

    if not code:
        print("인가 코드가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    success = request_token(code)
    sys.exit(0 if success else 1)
