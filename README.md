# 다나와 실시간 최저가 알림 봇 (lowprice)

다나와에서 상품의 실시간 최저가를 검색하고, 설정된 목표가 이하일 경우 카카오톡 '나에게 보내기'로 알림을 전송하는 봇입니다.

## 기능
1. **다나와 실시간 검색**: 광고 상품 필터링 및 실구매가(배송비 포함) 기준 최저가 TOP 3 추출
2. **목표가 판정**: 1위 가격이 목표 가격 이하일 때만 특가 판정
3. **카카오톡 나에게 보내기 알림**:
   - 상품명, 가격, 쇼핑몰, 리뷰 수 포함
   - '구매하러 가기' 링크 버튼 제공
   - 리프레시 토큰을 이용한 액세스 토큰 자동 갱신 지원

## 설치 및 설정
1. 필요한 라이브러리 설치:
   ```bash
   pip install beautifulsoup4
   ```
2. `.env` 파일 설정:
   ```env
   KAKAO_REST_API_KEY=your_rest_api_key
   KAKAO_CLIENT_SECRET=your_client_secret
   KAKAO_REFRESH_TOKEN=your_refresh_token
   KAKAO_ACCESS_TOKEN=your_access_token
   ```

## 실행 방법
```bash
python lowerprice_bot.py
```
