#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lowerprice_bot.py
다나와 쇼핑 검색 스킬을 이용한 맥주(카스 24개) 최저가 알림 봇 (카카오톡 알림 연동)

요구사항:
1. 다나와 쇼핑 검색 스킬로 "카스 24개"를 최저가 순으로 검색
2. 최저가 순서로 상품 3개를 상품명, 가격, 쇼핑몰, 리뷰수, 링크와 함께 화면에 보기 좋게 출력
3. 반환된 광고 상품은 제거하고, 진짜 상품만 필터링
4. 1위 가격의 목표가 30,000원 이하인지 확인 후 다음 중 하나를 함께 출력
   - 목표가 이하일 때 : " [특가발견] 목표 가격 이하입니다."
   - 목표가 초과일 때 : "[유지] 아직 목표 가격 보다 비싸요!"
5. 잘못된 값을 가져올 경우 지어내지 말고, 무엇이 잘못되었는지 그대로 알려주고 멈춤
"""

import sys
import os
import re
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from html import unescape
from typing import Dict, List, Any, Optional, Tuple

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ [오류 발생] beautifulsoup4 라이브러리가 설치되어 있지 않습니다.", file=sys.stderr)
    print("설치 명령: python -m pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

# 설정 상수
QUERY = "카스 24개"
TARGET_PRICE = 30000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def clean_text(s: Optional[str]) -> str:
    """HTML 엔티티 및 불필요한 공백 제거"""
    if not s:
        return ""
    return " ".join(unescape(s).split())


def parse_int(s: Optional[str]) -> Optional[int]:
    """문자열에서 숫자만 추출하여 정수로 변환"""
    if not s:
        return None
    digits = re.sub(r"\D", "", str(s))
    return int(digits) if digits else None


def report_error_and_exit(title: str, reason: str, details: Optional[str] = None) -> None:
    """잘못된 값이나 오류 발생 시 임의의 데이터를 지어내지 않고 원인을 알리고 종료 (요구사항 5)"""
    print("\n" + "=" * 65, file=sys.stderr)
    print(f"❌ [오류 발생] {title}", file=sys.stderr)
    print(f"📌 원인: {reason}", file=sys.stderr)
    if details:
        print(f"🔍 상세 내용:\n{details}", file=sys.stderr)
    print("-" * 65, file=sys.stderr)
    print("⚠️  규정에 따라 가짜 데이터를 생성하지 않고 스크립트를 즉시 중단합니다.", file=sys.stderr)
    print("=" * 65 + "\n", file=sys.stderr)
    sys.exit(1)


def fetch_url(url: str, post_data: Optional[dict] = None, referer: Optional[str] = None) -> str:
    """HTTP 요청 헬퍼"""
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    body = None
    if post_data is not None:
        body = urllib.parse.urlencode(post_data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        headers["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        headers["Referer"] = referer

    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            if status != 200:
                report_error_and_exit(
                    "HTTP 상태 오류",
                    f"서버가 비정상 상태 코드(HTTP {status})를 반환했습니다.",
                    f"요청 URL: {url}"
                )
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as he:
        report_error_and_exit(
            "HTTP 요청 오류",
            f"HTTP {he.code} {he.reason}",
            f"요청 URL: {url}"
        )
    except urllib.error.URLError as ue:
        report_error_and_exit(
            "네트워크 연결 오류",
            f"다나와 서버에 접속할 수 없습니다: {ue.reason}",
            f"요청 URL: {url}"
        )
    except Exception as ex:
        report_error_and_exit(
            "예기치 않은 네트워크 오류",
            f"{type(ex).__name__}: {ex}",
            f"요청 URL: {url}"
        )


def search_danawa_candidates(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    1. 다나와 쇼핑 검색 스킬 명세에 따른 상품 후보 검색
    URL: https://search.danawa.com/dsearch.php?query=...
    """
    search_url = f"https://search.danawa.com/dsearch.php?query={urllib.parse.quote(query)}"
    print(f"📡 다나와 쇼핑 검색 스킬 호출 중... (검색어: '{query}')")
    
    html = fetch_url(search_url)
    if not html:
        report_error_and_exit("검색 결과 수신 실패", "다나와 검색 응답 본문이 비어 있습니다.")

    soup = BeautifulSoup(html, "html.parser")
    items = []

    # 최신 다나와 Next.js 렌더링 상품 카드 (li[data-product-seq]) 탐색
    raw_elements = soup.select("li[data-product-seq]")
    if not raw_elements:
        # 기존 레거시 마크업 (li.prod_item) 탐색
        raw_elements = soup.select("li.prod_item")

    if not raw_elements:
        report_error_and_exit(
            "상품 목록 파싱 실패",
            "검색 결과 페이지에서 상품 카드를 찾을 수 없습니다. (다나와 HTML 구조 변경 또는 검색 차단 가능성)",
            f"응답 길이: {len(html)} bytes"
        )

    for el in raw_elements:
        pcode = el.get("data-product-seq") or (el.get("id") or "").replace("productItem", "")
        if not pcode:
            continue

        # 3. 광고 상품 판별 및 제거 (is_ad 플래그 확인)
        classes = el.get("class") or []
        is_ad = False
        if any("ad" in c.lower() for c in classes) or el.select_one(".ico_ad, .ad_header, [class*='ad_']"):
            is_ad = True
        for txt in el.stripped_strings:
            if txt in ("AD", "광고"):
                is_ad = True
                break

        # 상품명 추출
        title_el = el.select_one('p a[href*="pcode="]') or el.select_one('a[href*="pcode="]') or el.select_one('.prod_name a')
        title = clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
        if not title or title == "이미지 보기":
            for a in el.select('a[href*="pcode="]'):
                t = clean_text(a.get_text(" ", strip=True))
                if t and t != "이미지 보기" and "리뷰수" not in t and "원" not in t:
                    title = t
                    break

        # 리뷰수 추출
        review_count = 0
        review_el = el.select_one('a[data-testid="ProductListShopReview"]') or el.select_one('a[href*="bookmark_cm_opinion"]') or el.select_one('.prod_sub_meta')
        if review_el:
            rev_match = re.search(r"\((\d+[\d,]*)\+?\)", review_el.get_text())
            if rev_match:
                review_count = parse_int(rev_match.group(1)) or 0

        # 카드에 표기된 기본 최저가
        card_price = None
        for span in el.select("span, em.prc_c, strong"):
            txt = span.get_text(strip=True)
            if re.match(r"^[\d,]+원$", txt):
                card_price = parse_int(txt)
                break

        items.append({
            "pcode": str(pcode),
            "title": title,
            "card_price": card_price,
            "review_count": review_count,
            "is_ad": is_ad,
            "product_url": f"https://prod.danawa.com/info/?pcode={pcode}"
        })

        if len(items) >= limit:
            break

    return items


def get_lowest_offer(pcode: str, referer_url: str) -> Optional[Dict[str, Any]]:
    """
    다나와 가격비교 AJAX를 호출해 판매처(쇼핑몰), 배송비 포함 실구매가, 구매 링크 조회
    엔드포인트: https://prod.danawa.com/info/ajax/getAllPriceCompareMallList.ajax.php
    """
    ajax_url = "https://prod.danawa.com/info/ajax/getAllPriceCompareMallList.ajax.php"
    post_data = {
        "pcode": str(pcode),
        "cate1": "0",
        "cate2": "0",
        "cate3": "0",
        "cate4": "0"
    }
    
    html = fetch_url(ajax_url, post_data=post_data, referer=referer_url)
    soup = BeautifulSoup(html, "html.parser")

    # 쇼핑몰 오퍼 목록 파싱 (div.diff_item 또는 tr.diff_item)
    offers = []
    for tr in soup.select(".diff_item, tr[class*='diff_item']"):
        # 쇼핑몰명 추출
        mall_img = tr.select_one(".d_mall img, .mall img")
        mall_txt = tr.select_one(".d_mall .mall_name, .d_mall a, .mall .mall_name, .mall")
        mall = (mall_img.get("alt") if mall_img else None) or (mall_txt.get_text(strip=True) if mall_txt else "다나와 제휴몰")

        # 가격 추출
        prc_el = tr.select_one(".prc_c, .prc_t, em.prc_c, em.prc_t, .price em")
        price = parse_int(prc_el.get_text() if prc_el else None)
        if price is None:
            continue

        # 배송비 추출
        ship_el = tr.select_one(".ship, .delivery")
        shipping = clean_text(ship_el.get_text(" ", strip=True)) if ship_el else ""
        shipping_fee = 0 if "무료" in shipping else (parse_int(shipping) or 0)

        # 실구매가 (상품가 + 배송비)
        total_price = price + shipping_fee

        # 구매 링크
        link_el = tr.select_one("a.priceCompareBuyLink, a.btn_buy, a.memo_link, a")
        link = link_el.get("href") if link_el else ""
        if link and link.startswith("//"):
            link = "https:" + link
        elif link and link.startswith("/"):
            link = "https://prod.danawa.com" + link

        offers.append({
            "mall": clean_text(mall),
            "price": price,
            "shipping_fee": shipping_fee,
            "total_price": total_price,
            "url": link
        })

    if not offers:
        return None

    # 실구매가(배송비 포함) 기준 오름차순 정렬
    offers.sort(key=lambda o: o["total_price"])
    return offers[0]


def process_products(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    광고 제거, 각 상품의 쇼핑몰별 최저가 오퍼 조회, 최저가 순 정렬 후 상위 3개 반환
    """
    real_candidates = []
    ad_count = 0

    for c in candidates:
        # 광고 상품 배제 (요구사항 3)
        if c["is_ad"]:
            ad_count += 1
            continue

        # 제목에 '카스'가 포함되어 있고, 에너지음료 등 맥주와 무관한 상품 제외 (요구사항 3: 맥주 진짜 상품 필터링)
        if "카스" not in c["title"]:
            continue
        if "에너지" in c["title"] or ("맥주" not in c["title"] and "오비" not in c["title"]):
            continue

        real_candidates.append(c)

    print(f"📊 [필터링 현황] 검색된 후보: {len(candidates)}개 | 광고 제거: {ad_count}개 | 유효 상품: {len(real_candidates)}개")

    if not real_candidates:
        report_error_and_exit("유효 상품 없음", "광고를 제외하고 남은 유효한 '카스' 상품이 없습니다.")

    processed = []
    for item in real_candidates:
        pcode = item["pcode"]
        offer = get_lowest_offer(pcode, item["product_url"])
        
        if offer:
            final_price = offer["total_price"]
            mall_name = offer["mall"]
            url = offer["url"] or item["product_url"]
        else:
            final_price = item["card_price"]
            mall_name = "다나와 최저가"
            url = item["product_url"]

        if not final_price:
            # 가격 정보가 없는 상품은 신뢰할 수 없으므로 제외
            continue

        processed.append({
            "pcode": pcode,
            "title": item["title"],
            "price": final_price,
            "mall_name": mall_name,
            "review_count": item["review_count"],
            "url": url
        })

    if not processed:
        report_error_and_exit("가격 데이터 부재", "유효한 가격 정보를 가진 상품이 없습니다.")

    # 1. 최저가 순으로 정렬
    processed.sort(key=lambda x: x["price"])

    # 2. 상위 3개 상품 반환
    return processed[:3]


def load_env_file(filepath: Optional[str] = None) -> Dict[str, str]:
    """.env 파일 파싱하여 딕셔너리로 반환 (키 하드코딩 방지)"""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 한 줄에 공백으로 여러 KEY=VALUE가 있는 경우도 처리
                parts = line.split()
                for part in parts:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
    except Exception as e:
        print(f"⚠️ [.env 파일 읽기 오류] {e}", file=sys.stderr)
    return env_vars


def update_env_file(filepath: str, key: str, value: str) -> None:
    """.env 파일의 특정 키 값을 갱신하거나 없으면 추가"""
    lines = []
    found = False
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} "):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def refresh_kakao_access_token(env_path: str, env_vars: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """리프레시 토큰을 이용해 카카오 액세스 토큰 갱신"""
    refresh_token = env_vars.get("KAKAO_REFRESH_TOKEN")
    client_id = env_vars.get("KAKAO_REST_API_KEY")
    client_secret = env_vars.get("KAKAO_CLIENT_SECRET")

    if not refresh_token:
        return None, ".env 파일에 KAKAO_REFRESH_TOKEN이 없습니다."
    if not client_id:
        return None, ".env 파일에 KAKAO_REST_API_KEY가 없습니다."

    token_url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token
    }
    if client_secret:
        data["client_secret"] = client_secret

    post_body = urllib.parse.urlencode(data).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    req = urllib.request.Request(token_url, data=post_body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            new_access_token = res_json.get("access_token")
            if not new_access_token:
                return None, f"토큰 갱신 응답에 access_token이 없습니다: {body}"

            # .env 파일에 새 액세스 토큰 저장
            update_env_file(env_path, "KAKAO_ACCESS_TOKEN", new_access_token)
            env_vars["KAKAO_ACCESS_TOKEN"] = new_access_token

            # 만약 refresh_token도 새로 갱신되어 발급되었으면 저장
            new_refresh_token = res_json.get("refresh_token")
            if new_refresh_token:
                update_env_file(env_path, "KAKAO_REFRESH_TOKEN", new_refresh_token)
                env_vars["KAKAO_REFRESH_TOKEN"] = new_refresh_token

            return new_access_token, None
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", "replace")
        return None, f"HTTP {he.code}: {err_body}"
    except Exception as ex:
        return None, f"{type(ex).__name__}: {ex}"


def send_kakao_alert(product: Dict[str, Any]) -> bool:
    """
    1위 특가 상품 정보를 카카오톡 '나에게 보내기'로 전송
    요구사항:
    1. 상품명, 가격, 쇼핑몰 이름, 리뷰 수를 넣고 '구매하러 가기' 버튼으로 링크 설정
    2. 알림을 못 보냈으면 보낸 척 하지 말고 무엇이 잘못되었는지 그대로 안내
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        print("\n" + "=" * 65, file=sys.stderr)
        print("❌ [카카오톡 알림 실패] 프로젝트 폴더에 .env 파일이 존재하지 않습니다.", file=sys.stderr)
        print(f"📌 예상 경로: {env_path}", file=sys.stderr)
        print("=" * 65 + "\n", file=sys.stderr)
        return False

    env_vars = load_env_file(env_path)
    access_token = env_vars.get("KAKAO_ACCESS_TOKEN")
    refresh_token = env_vars.get("KAKAO_REFRESH_TOKEN")

    if not access_token and not refresh_token:
        print("\n" + "=" * 65, file=sys.stderr)
        print("❌ [카카오톡 알림 실패] .env 파일에 카카오 인증 토큰이 설정되어 있지 않습니다.", file=sys.stderr)
        print("📌 원인: .env 파일에 KAKAO_REFRESH_TOKEN 또는 KAKAO_ACCESS_TOKEN 항목이 필요합니다.", file=sys.stderr)
        print("=" * 65 + "\n", file=sys.stderr)
        return False

    # 액세스 토큰이 없고 리프레시 토큰만 있는 경우 바로 갱신 시도
    if not access_token and refresh_token:
        print("🔄 [카카오톡] 액세스 토큰이 없어 리프레시 토큰으로 자동 발급을 시도합니다...")
        access_token, err = refresh_kakao_access_token(env_path, env_vars)
        if not access_token:
            print("\n" + "=" * 65, file=sys.stderr)
            print("❌ [카카오톡 알림 실패] 카카오 토큰 발급에 실패하여 알림을 전송할 수 없습니다.", file=sys.stderr)
            print(f"📌 실패 원인: {err}", file=sys.stderr)
            print("=" * 65 + "\n", file=sys.stderr)
            return False

    # 요구사항 2: 상품명, 가격, 쇼핑몰 이름, 리뷰 수를 넣고 '구매하러 가기' 버튼으로 링크 설정
    text_content = (
        f"🍺 [특가발견] 카스 24개 목표가 이하!\n\n"
        f"• 상품명: {product['title']}\n"
        f"• 가격: {product['price']:,}원\n"
        f"• 쇼핑몰: {product['mall_name']}\n"
        f"• 리뷰수: {product['review_count']:,}개"
    )

    template_object = {
        "object_type": "text",
        "text": text_content,
        "link": {
            "web_url": product["url"],
            "mobile_web_url": product["url"]
        },
        "button_title": "구매하러 가기",
        "buttons": [
            {
                "title": "구매하러 가기",
                "link": {
                    "web_url": product["url"],
                    "mobile_web_url": product["url"]
                }
            }
        ]
    }

    memo_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    post_data = urllib.parse.urlencode({
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }).encode("utf-8")

    def _do_send(token: str) -> Tuple[bool, int, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
        }
        req = urllib.request.Request(memo_url, data=post_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_text = resp.read().decode("utf-8")
                res = json.loads(resp_text)
                if res.get("result_code") == 0:
                    return True, 200, resp_text
                return False, resp.getcode(), resp_text
        except urllib.error.HTTPError as he:
            err_text = he.read().decode("utf-8", "replace")
            return False, he.code, err_text
        except Exception as ex:
            return False, 0, str(ex)

    # 1차 전송 시도
    success, code, res_text = _do_send(access_token)

    # 401 Unauthorized(토큰 만료)인 경우 리프레시 토큰으로 자동 갱신 후 1회 재시도
    if not success and code == 401 and refresh_token:
        print("🔄 [카카오톡] 액세스 토큰 만료를 감지하여 리프레시 토큰으로 갱신 후 재전송합니다...")
        new_token, err = refresh_kakao_access_token(env_path, env_vars)
        if new_token:
            access_token = new_token
            success, code, res_text = _do_send(access_token)
        else:
            print("\n" + "=" * 65, file=sys.stderr)
            print("❌ [카카오톡 알림 실패] 토큰 만료 후 갱신 실패로 전송하지 못했습니다.", file=sys.stderr)
            print(f"📌 갱신 오류: {err}", file=sys.stderr)
            print("=" * 65 + "\n", file=sys.stderr)
            return False

    # 요구사항 3: 알림을 못 보냈으면 보낸 척 하지 말고 무엇이 잘못되었는지 그대로 알려줌
    if success:
        print("💬 [카카오톡 알림] 1위 특가 상품 알림을 카카오톡 '나에게 보내기'로 성공적으로 전송했습니다!\n")
        return True
    else:
        print("\n" + "=" * 65, file=sys.stderr)
        print("❌ [카카오톡 알림 실패] 메시지를 카카오톡으로 전송하지 못했습니다.", file=sys.stderr)
        print(f"📌 HTTP 상태 코드: {code}", file=sys.stderr)
        print(f"📌 카카오 API 응답 내용:\n{res_text}", file=sys.stderr)
        print("=" * 65 + "\n", file=sys.stderr)
        return False


def print_results(top_products: List[Dict[str, Any]]) -> bool:
    """화면에 상품 3개 정보 및 1위 목표가(30,000원) 판정 출력 (요구사항 2, 4)"""
    print("\n" + "=" * 65)
    print(f"🍺  [다나와 '카스 24개' 최저가 TOP {len(top_products)}]")
    print("=" * 65)

    for rank, p in enumerate(top_products, start=1):
        print(f"\n[{rank}위] {p['title']}")
        print(f"  • 가격     : {p['price']:,}원")
        print(f"  • 쇼핑몰   : {p['mall_name']}")
        print(f"  • 리뷰수   : {p['review_count']:,}개")
        print(f"  • 링크     : {p['url']}")
        print("-" * 65)

    # 4. 1위 가격이 30,000원 이하인지 확인
    top_price = top_products[0]["price"]
    print("\n" + "=" * 65)
    print(f"🎯 [목표가 판정] 기준 가격: {TARGET_PRICE:,}원 | 현재 1위 실구매가: {top_price:,}원")
    
    is_under_target = (top_price <= TARGET_PRICE)
    if is_under_target:
        print(" [특가발견] 목표 가격 이하입니다.")
    else:
        print("[유지] 아직 목표 가격 보다 비싸요!")
    print("=" * 65 + "\n")

    return is_under_target


def main():
    print(f"🚀 '카스 24개' 다나와 실시간 최저가 조회를 시작합니다...\n")
    
    # 1. 다나와 쇼핑 검색으로 상품 후보 수집
    candidates = search_danawa_candidates(QUERY, limit=15)

    # 2 & 3. 광고 상품 제거 및 실구매가 오퍼 기준 최저가 상위 3개 추출
    top_3 = process_products(candidates)

    # 4. 화면 출력 및 목표가 판정
    is_under_target = print_results(top_3)

    # 5. 요구사항 1: 1위 가격이 목표가 이하일 때만 카카오톡으로 알림 전송 (초과 시 화면 출력만 하고 메시지 안 보냄)
    if is_under_target:
        send_kakao_alert(top_3[0])


if __name__ == "__main__":
    main()
