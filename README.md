# 미발송 주문 대시보드

네이버 스마트스토어 + 아임웹 미발송 주문을 실시간으로 집계하는 웹 대시보드입니다.

---

## 파일 구조

```
order-dashboard/
├── main.py              # FastAPI 서버 (API 프록시)
├── requirements.txt     # Python 패키지
├── Procfile             # Railway 실행 명령
├── railway.json         # Railway 배포 설정
└── static/
    └── index.html       # 웹 대시보드 UI
```

---

## Railway 배포 방법 (5분 완성)

### 1단계: GitHub 저장소 생성

```bash
cd order-dashboard
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/YOUR_ID/order-dashboard.git
git push -u origin main
```

### 2단계: Railway 연결

1. [railway.app](https://railway.app) 접속 → GitHub 로그인
2. **New Project → Deploy from GitHub repo** 선택
3. `order-dashboard` 저장소 선택
4. 자동으로 빌드 및 배포 시작 (약 1~2분)
5. **Settings → Networking → Generate Domain** 클릭 → URL 발급

### 3단계: 접속 확인

발급된 URL(예: `https://order-dashboard-xxx.up.railway.app`)로 접속하면 대시보드가 열립니다.

---

## API 키 발급 방법

### 네이버 스마트스토어

1. [스마트스토어 센터](https://sell.smartstore.naver.com) 로그인
2. **판매자 정보 → API 관리 → 애플리케이션 등록**
3. Client ID / Client Secret 복사

### 아임웹

1. [아임웹 관리자](https://www.imweb.me) 로그인
2. **쇼핑몰 설정 → 외부 서비스 연동 → API 연동**
3. API Key / Secret Key 복사

---

## 로컬 테스트 방법

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# http://localhost:8000 접속
```

---

## 미발송 주문 기준

| 채널 | 집계 상태 |
|------|-----------|
| 네이버 스마트스토어 | 결제완료 (PAYMENT_DONE), 상품준비중 (PREPARING_PRODUCT) |
| 아임웹 | 주문확인 (order_confirm), 배송준비중 (ready_delivery) |

---

## 주요 기능

- 네이버 / 아임웹 동시 조회 및 상품별 수량 합산
- 채널별 필터링 (네이버만 / 아임웹만 / 중복)
- 수량 기준 정렬
- CSV 다운로드
- 조회 기간 선택 (7일 / 14일 / 30일 / 60일 / 90일)
