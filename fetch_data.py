import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

# 매일 새벽에 미리 캐싱(저장)해둘 주요 티커 목록
TARGET_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA",
    "QQQ", "QLD", "TQQQ", "SPY", "VOO",
    "005930.KS", "000660.KS", "373220.KS", "005380.KS"
]

def fetch_and_save():
    os.makedirs("data", exist_ok=True)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=365 * 10) # 최근 10년치 저장

    print(f"Data fetching started: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

    for ticker in TARGET_TICKERS:
        try:
            print(f"Fetching {ticker}...", end=" ")
            data = yf.download(ticker, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'), progress=False)
            
            if data.empty:
                print("No data.")
                continue

            # yfinance 최신 다중 인덱스 구조 안전망 처리
            if isinstance(data.columns, pd.MultiIndex):
                adj_close = data['Close'].iloc[:, 0].dropna()
            else:
                adj_close = data['Close'].dropna()

            if adj_close.empty:
                print("No close data.")
                continue

            result_list = []
            for date, price in adj_close.items():
                result_list.append({
                    "date": date.strftime('%Y-%m-%d'),
                    "close": float(price)
                })

            payload = {
                "updated": end_date.strftime('%Y-%m-%d'),
                "data": result_list
            }

            file_path = f"data/{ticker}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            print(f"Saved! ({len(result_list)} days)")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    fetch_and_save()
