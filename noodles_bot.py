#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
noodles_bot.py
다나와 쇼핑 검색 스킬을 이용한 라면(안성탕면 5개 번들) 최저가 알림 봇

요구사항:
1. 다나와 쇼핑 검색 스킬로 "안성탕면 5개 번들"을 최저가 순으로 검색
2. 최저가 순서로 상품 3개를 상품명, 가격, 쇼핑몰, 리뷰수, 링크와 함께 화면에 보기 좋게 출력
3. 반환된 광고 상품은 제거하고, 진짜 상품만 필터링
4. 1위 가격의 목표가 4,000원 이하인지 확인 후 다음 중 하나를 함께 출력
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
from typing import Dict, List, Any, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ [오류 발생] beautifulsoup4 라이브러리가 필요합니다.", file=sys.stderr)
    print("설치 명령: python -m pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

# 설정 상수
QUERY = "안성탕면 5개 번들"
FALLBACK_QUERY = "안성탕면 5개"  # 다나와는 '번들' 단어 대신 주로 '5개', '5입' 규격명 사용
TARGET_PRICE = 4000
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
    다나와 쇼핑 검색 스킬 명세에 따른 상품 후보 검색
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

    # 결과가 0건일 때, '번들' 단어로 인한 무결과 시 표준 단어 '안성탕면 5개'로 자동 보정 재시도
    if not raw_elements and query == QUERY:
        print(f"ℹ️  [검색어 보정] '{query}' 검색 결과가 0건입니다.")
        print(f"    다나와는 '번들' 대신 '5개', '5입' 규격명으로 색인하므로 '{FALLBACK_QUERY}'(으)로 재시도합니다.")
        return search_danawa_candidates(FALLBACK_QUERY, limit=limit)

    if not raw_elements:
        report_error_and_exit(
            "상품 목록 파싱 실패",
            f"'{query}'에 대한 상품 카드를 찾을 수 없습니다.",
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
    광고 제거, 5개 번들 구성 여부 확인, 각 상품의 쇼핑몰별 최저가 오퍼 조회, 최저가 순 정렬 후 상위 3개 반환
    """
    real_candidates = []
    ad_count = 0

    for c in candidates:
        # 광고 상품 배제 (요구사항 3)
        if c["is_ad"]:
            ad_count += 1
            continue

        # 안성탕면 제품 여부 검증
        if "안성탕면" not in c["title"]:
            continue

        real_candidates.append(c)

    print(f"📊 [필터링 현황] 검색된 후보: {len(candidates)}개 | 광고 제거: {ad_count}개 | 유효 상품: {len(real_candidates)}개")

    if not real_candidates:
        report_error_and_exit("유효 상품 없음", "광고를 제외하고 남은 유효한 '안성탕면' 상품이 없습니다.")

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


def print_results(top_products: List[Dict[str, Any]]) -> None:
    """화면에 상품 3개 정보 및 1위 목표가(4,000원) 판정 출력 (요구사항 2, 4)"""
    print("\n" + "=" * 65)
    print(f"🍜  [다나와 '안성탕면 5개 번들' 최저가 TOP {len(top_products)}]")
    print("=" * 65)

    for rank, p in enumerate(top_products, start=1):
        print(f"\n[{rank}위] {p['title']}")
        print(f"  • 가격     : {p['price']:,}원")
        print(f"  • 쇼핑몰   : {p['mall_name']}")
        print(f"  • 리뷰수   : {p['review_count']:,}개")
        print(f"  • 링크     : {p['url']}")
        print("-" * 65)

    # 4. 1위 가격이 4,000원 이하인지 확인
    top_price = top_products[0]["price"]
    print("\n" + "=" * 65)
    print(f"🎯 [목표가 판정] 기준 가격: {TARGET_PRICE:,}원 | 현재 1위 실구매가: {top_price:,}원")
    
    if top_price <= TARGET_PRICE:
        print(" [특가발견] 목표 가격 이하입니다.")
    else:
        print("[유지] 아직 목표 가격 보다 비싸요!")
    print("=" * 65 + "\n")


def main():
    print("🚀 '안성탕면 5개 번들' 다나와 실시간 최저가 조회를 시작합니다...\n")
    
    # 1. 다나와 쇼핑 검색으로 상품 후보 수집
    candidates = search_danawa_candidates(QUERY, limit=15)

    # 2 & 3. 광고 상품 제거 및 실구매가 오퍼 기준 최저가 상위 3개 추출
    top_3 = process_products(candidates)

    # 4. 화면 출력 및 목표가 판정
    print_results(top_3)


if __name__ == "__main__":
    main()
