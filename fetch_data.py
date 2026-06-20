"""
fetch_data.py
GitHub Actions에서 실행되는 데이터 수집 스크립트.
Yahoo Finance에서 주요 종목 데이터를 받아 data/*.json 으로 저장한다.
"""

import yfinance as yf
import json
import os
from datetime import datetime, timedelta

# ── 수집할 종목 목록 ────────────────────────────────────────────────────
TICKERS = [
    # 미국 ETF (레버리지 포함)
    "QQQ", "QLD", "TQQQ", "SQQQ",
    "SPY", "VOO", "IVV", "SSO", "UPRO",
    "DIA", "IWM",
    "SOXX", "SOXL",
    "SCHD", "TLT", "GLD", "SLV", "USO", "VNQ",
    "XLV", "XLE", "XLF", "XLK",
    "KWEB", "INDA", "VNM",
    # 미국 개별주
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AVGO", "COST", "NFLX",
    "AMD", "INTC", "QCOM", "ASML", "TSM",
    "PEP", "KO", "WMT", "SBUX", "DIS",
    "ORCL", "CRM", "ADBE",
    "UBER", "PLTR", "SNOW", "SHOP", "SPOT",
    "ABNB", "COIN", "RBLX", "IONQ", "RGTI",
    "SOFI", "HOOD",
    "BRK-B", "JPM", "BAC", "GS", "V", "MA",
    "JNJ", "PFE", "MRK", "XOM", "CVX",
    # 한국 주요 종목
    "005930.KS", "000660.KS", "373220.KS", "207940.KS",
    "005380.KS", "000270.KS", "068270.KS", "005490.KS",
    "105560.KS", "035420.KS", "028260.KS", "006400.KS",
    "055550.KS", "035720.KS", "051910.KS", "012330.KS",
    "086790.KS", "138040.KS", "323410.KS", "259960.KS",
    "247540.KQ", "086520.KQ",
]

# ── 수집 기간 ───────────────────────────────────────────────────────────
START_DATE = "2010-01-01"
END_DATE   = datetime.today().strftime("%Y-%m-%d")

# ── 출력 디렉토리 ───────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)

# ── KRW 종목 USD 환산 기준 ──────────────────────────────────────────────
KRW_USD_RATE = 1500.0


def fetch_and_save(ticker: str):
    print(f"[fetch] {ticker} ...", end=" ", flush=True)
    try:
        df = yf.download(
            ticker,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            repair=False,
            progress=False,
            timeout=30,
        )

        if df.empty:
            print("❌ 데이터 없음")
            return

        # Close 컬럼 추출 (MultiIndex 대응)
        if isinstance(df.columns, __import__("pandas").MultiIndex):
            close_series = df["Close"].iloc[:, 0]
        else:
            close_series = df["Close"] if "Close" in df.columns else df.iloc[:, 0]

        close_series = close_series.dropna()
        if close_series.empty:
            print("❌ Close 데이터 없음")
            return

        # KRW 종목은 USD 환산
        if ticker.endswith(".KS") or ticker.endswith(".KQ"):
            close_series = close_series / KRW_USD_RATE

        # JSON 직렬화
        records = [
            {"date": str(dt.date()), "close": round(float(price), 6)}
            for dt, price in close_series.items()
            if price > 0
        ]

        payload = {
            "ticker":  ticker,
            "updated": END_DATE,
            "start":   START_DATE,
            "count":   len(records),
            "data":    records,
        }

        # 파일 저장 (슬래시 제거: BRK-B → BRK-B.json, 005930.KS → 005930.KS.json)
        filename = f"data/{ticker}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

        print(f"✅ {len(records)}일 저장 → {filename}")

    except Exception as e:
        print(f"⚠️  오류: {e}")


def main():
    print(f"=== 데이터 수집 시작: {END_DATE} ===")
    print(f"수집 기간: {START_DATE} ~ {END_DATE}")
    print(f"수집 종목: {len(TICKERS)}개\n")

    for ticker in TICKERS:
        fetch_and_save(ticker)

    # 수집 결과 메타 파일 생성
    meta = {
        "updated": END_DATE,
        "start":   START_DATE,
        "tickers": TICKERS,
        "count":   len(TICKERS),
    }
    with open("data/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\n=== 완료: data/meta.json 생성 ===")


if __name__ == "__main__":
    main()
