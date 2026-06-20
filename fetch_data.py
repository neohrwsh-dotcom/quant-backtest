# ============================================================
# 퀀트 백테스팅 대시보드 v5.1 (한국 주식 / 한글 검색 버그 수정)
# ============================================================
# 변경 이력:
#   v5.1 (한국주식·한글 검색 버그 수정)
#     - resolve_ticker: 유니코드 NFC 정규화 추가 → 한글 입력 완전 대응
#     - _extract_close_series: 최신 yfinance 2.x MultiIndex 구조 완전 재작성
#       (level별 컬럼 직접 탐색, ticker 코드 부분매칭 포함)
#     - _fetch_kr_ticker: FDR 컬럼명 대소문자 무시 매칭 + 수치형 첫컬럼 fallback
#       history() 반환 MultiIndex 처리를 _get_close_from_hist()로 분리
#     - _fetch_us_batch: yf.download() 파라미터를 버전별 호환(try/except)으로 수정
#       (threads/repair 파라미터가 yfinance 2.x에서 제거된 문제 대응)
#
#   v6 (버그 수정)
#     ─ yfinance 2.x group_by/threads 파라미터 완전 제거 (_yf_download_safe)
#     ─ _extract_close_series: MultiIndex level name 'Price'/'Ticker' 완전 대응
#     ─ _fetch_kr_ticker: _fdr_close + _history_close 헬퍼로 버전 무관 추출
#     ─ FDR 컬럼 추출: 수치형 첫 컬럼 fallback 추가
#     ─ yf.Ticker().history(): 튜플 컬럼명 포함 모든 구조 대응
#   v5 (속도 최적화)
#     - US 종목: yf.download() 배치 1회 요청 + threads=True
#     - KR 종목(.KS/.KQ): yf.Ticker().history() 개별 (배치보다 안정적)
#     - repair=False → 불필요한 추가 HTTP 제거
#     - in-memory 캐시(_PRICE_CACHE): 동일 종목·기간 재요청 즉시 반환
#     - _safe_tz_strip(): tz-aware UTC 인덱스 → tz-naive 안전 변환
#     - _extract_close_series(): MultiIndex (Price×Ticker / Ticker×Price)
#       모든 구조 대응 + 대소문자 무시 매칭
#     - KR 누락 시 yf.download 2차, FinanceDataReader 3차 fallback
#     - 타이밍 로그(DEBUG=True 시) 로 병목 측정 가능
#     - Gradio UI 완전 보존 (달력 클릭 + 텍스트 입력 병행)
#     - 거치식/적립식 ROI 로직 완전 보존
# ============================================================

# ── 패키지 설치 ─────────────────────────────────────────────
import subprocess, sys

def pip_install(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])

pip_install("yfinance", "gradio", "plotly", "finance-datareader", "requests")

# ── 임포트 ──────────────────────────────────────────────────
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import plotly.graph_objects as go
import gradio as gr
import pandas as pd
import numpy as np
from datetime import datetime, date
import threading
import time

# ── 디버그 플래그 (타이밍 로그 on/off) ──────────────────────
DEBUG = True

def dprint(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# ── 한글 종목명 사전 ─────────────────────────────────────────
BASE_NAME_TO_TICKER = {
    # 미국 빅테크 & 주요 주식
    "애플": "AAPL", "마이크로소프트": "MSFT", "마소": "MSFT",
    "엔비디아": "NVDA", "알파벳": "GOOGL", "구글": "GOOGL",
    "아마존": "AMZN", "메타": "META", "페이스북": "META",
    "테슬라": "TSLA", "브로드컴": "AVGO", "코스트코": "COST",
    "넷플릭스": "NFLX", "암드": "AMD", "펩시": "PEP",
    "코카콜라": "KO", "시스코": "CSCO", "어도비": "ADBE",
    "인텔": "INTC", "퀄컴": "QCOM", "월마트": "WMT",
    "스타벅스": "SBUX", "디즈니": "DIS", "오라클": "ORCL",
    "우버": "UBER", "팔란티어": "PLTR", "스노우플레이크": "SNOW",
    "세일즈포스": "CRM", "쇼피파이": "SHOP", "스포티파이": "SPOT",
    "에어비앤비": "ABNB", "코인베이스": "COIN", "로블록스": "RBLX",
    "아이온큐": "IONQ", "리게티": "RGTI", "ARM": "ARM",
    "소파이": "SOFI", "로빈후드": "HOOD",
    "버크셔": "BRK-B", "JP모건": "JPM", "뱅크오브아메리카": "BAC",
    "골드만삭스": "GS", "비자": "V", "마스터카드": "MA",
    "존슨앤존슨": "JNJ", "화이자": "PFE", "머크": "MRK",
    "엑슨모빌": "XOM", "쉐브론": "CVX", "ASML": "ASML", "TSMC": "TSM",
    # ETF
    "나스닥": "QQQ", "나스닥1배": "QQQ", "나스닥2배": "QLD",
    "나스닥3배": "TQQQ", "나스닥인버스": "SQQQ",
    "S&P500": "SPY", "SPY": "SPY", "VOO": "VOO", "IVV": "IVV",
    "다우": "DIA", "반도체": "SOXX", "반도체3배": "SOXL",
    "배당": "SCHD", "러셀2000": "IWM", "채권": "TLT",
    "금": "GLD", "은": "SLV", "원유": "USO", "부동산": "VNQ",
    "헬스케어": "XLV", "에너지": "XLE", "금융": "XLF", "기술": "XLK",
    "중국": "KWEB", "인도": "INDA", "베트남": "VNM",
    "레버리지S&P": "SSO", "3배S&P": "UPRO",
    # 한국 주요 종목
    "삼성전자": "005930.KS", "삼전": "005930.KS",
    "SK하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS", "엔솔": "373220.KS",
    "삼성바이오로직스": "207940.KS", "삼바": "207940.KS",
    "현대차": "005380.KS", "기아": "000270.KS",
    "셀트리온": "068270.KS", "POSCO홀딩스": "005490.KS",
    "포스코": "005490.KS", "KB금융": "105560.KS",
    "네이버": "035420.KS", "NAVER": "035420.KS",
    "삼성물산": "028260.KS", "삼성SDI": "006400.KS",
    "신한지주": "055550.KS", "카카오": "035720.KS",
    "LG화학": "051910.KS", "현대모비스": "012330.KS",
    "포스코퓨처엠": "003670.KS", "하나금융지주": "086790.KS",
    "메리츠금융지주": "138040.KS", "삼성생명": "032830.KS",
    "에코프로비엠": "247540.KQ", "에코프로": "086520.KQ",
    "카카오뱅크": "323410.KS", "크래프톤": "259960.KS",
    "HMM": "011200.KS", "한국전력": "015760.KS",
    "SK텔레콤": "017670.KS", "LG전자": "066570.KS",
    "두산에너빌리티": "034020.KS", "현대건설": "000720.KS",
    "삼성화재": "000810.KS", "미래에셋증권": "006800.KS",
    "SK이노베이션": "096770.KS", "롯데케미칼": "011170.KS",
    "한미약품": "128940.KS", "엔씨소프트": "036570.KS",
    "넷마블": "251270.KS", "카카오게임즈": "293490.KS",
}

# ── KRX 동적 로드 ─────────────────────────────────────────────
# FDR로 전체 KRX 종목 이름↔티커 매핑 빌드
# 로드 실패 시 내장 사전(BASE_NAME_TO_TICKER)만 사용
_KRX_MAP: dict = {}
_krx_lock = threading.Lock()

def load_krx_map() -> dict:
    global _KRX_MAP
    with _krx_lock:
        if _KRX_MAP:
            return _KRX_MAP
        result = {}
        try:
            import FinanceDataReader as fdr
            for market_code in ["KOSPI", "KOSDAQ"]:
                try:
                    df = fdr.StockListing(market_code)
                    suffix = ".KS" if market_code == "KOSPI" else ".KQ"
                    for _, row in df.iterrows():
                        # FDR 컬럼명이 버전마다 다름 → 여러 이름 시도
                        code = str(row.get("Code") or row.get("Symbol") or "").strip()
                        name = str(row.get("Name") or row.get("ISU_ABBRV") or "").strip()
                        if not code or not name:
                            continue
                        yf_ticker = f"{code}{suffix}"
                        result[name]      = yf_ticker   # 종목명 → 티커
                        result[code]      = yf_ticker   # 6자리 코드 → 티커
                        result[yf_ticker] = yf_ticker   # "005930.KS" → 그대로
                except Exception as e:
                    print(f"[KRX 로드 {market_code} 실패]: {e}")
            if result:
                _KRX_MAP = result
                print(f"[KRX 로드 완료] {len(result):,}개 매핑")
            else:
                print("[KRX 로드 실패 - 내장 사전만 사용]")
                _KRX_MAP = {}
        except Exception as e:
            print(f"[KRX 로드 실패 - 내장 사전만 사용]: {e}")
            _KRX_MAP = {}
    return _KRX_MAP


def resolve_ticker(raw: str) -> str:
    """
    입력 문자열 → yfinance 티커 심볼로 변환.
    우선순위:
      1) 내장 한글/영문 사전 (BASE_NAME_TO_TICKER)
      2) KRX 동적 사전 (FinanceDataReader로 빌드)
      3) 6자리 숫자 → "XXXXXX.KS"
      4) 이미 ".KS"/".KQ" 포함 → 그대로 반환
      5) 원본 대문자 반환 (미국 티커)
    """
    t = raw.strip().replace(" ", "")
    if not t:
        return t

    # 1) 내장 사전 (한글 포함) — 원본 그대로 먼저
    if t in BASE_NAME_TO_TICKER:
        return BASE_NAME_TO_TICKER[t]
    t_upper = t.upper()
    if t_upper in BASE_NAME_TO_TICKER:
        return BASE_NAME_TO_TICKER[t_upper]

    # 2) KRX 동적 사전
    krx = load_krx_map()
    if t in krx:
        return krx[t]
    if t_upper in krx:
        return krx[t_upper]

    # 3) 숫자 6자리 → .KS (코스피 기본 가정)
    if t.isdigit() and len(t) == 6:
        return t + ".KS"

    # 4) 이미 yfinance 한국 형식이면 그대로
    if ".KS" in t_upper or ".KQ" in t_upper:
        return t_upper

    # 5) 미국 티커로 간주
    return t_upper

# ============================================================
# 속도 개선 핵심: 데이터 다운로드 레이어
# ============================================================
# 설계 원칙:
#   1. in-memory 캐시 → 동일 요청 즉시 반환 (0ms)
#   2. US 종목: yf.download() 배치 1회 요청 + threads=True
#      - QLD/QQQ/TQQQ 3종목을 HTTP 1회로 처리
#   3. KR 종목: Ticker().history() 개별
#      - download()보다 KR 데이터 안정적, repair=False로 빠름
#   4. 배치 누락 시 개별 재시도 → 항상 데이터 보장
#   5. repair=False → 추가 HTTP 요청 완전 제거
# ============================================================

_PRICE_CACHE: dict = {}
_cache_lock = threading.Lock()


def _cache_key(tickers: list, start: str, end: str) -> tuple:
    return (tuple(sorted(tickers)), start, end)


def _safe_tz_strip(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """tz-aware/naive 상관없이 안전하게 tz-naive로 변환."""
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        return idx.tz_convert("UTC").tz_localize(None)
    return idx


def _extract_close_series(df: pd.DataFrame, ticker: str) -> pd.Series:
    """
    yfinance DataFrame에서 Close 시리즈 추출.
    ─────────────────────────────────────────────────────────────
    yfinance 버전별 반환 구조 4가지 모두 대응:
      A) MultiIndex (Price, Ticker) — yfinance ≥0.2.31 기본값
         level names: ['Price','Ticker']  or  lvl0에 'Close' 포함
      B) MultiIndex (Ticker, Price) — 구버전 group_by='ticker'
         level names: ['Ticker','Price']  or  lvl0에 ticker 포함
      C) MultiIndex level 1에 Price 이름
      D) 단일 Index — 단일 종목 download 또는 Ticker.history()
    ─────────────────────────────────────────────────────────────
    """
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)

    PRICE_COLS = ["Close", "Adj Close", "close", "adj close"]

    def _pick_close(subdf: pd.DataFrame) -> pd.Series:
        """단순 컬럼 DataFrame에서 Close 계열 컬럼 선택."""
        for c in PRICE_COLS:
            if c in subdf.columns:
                return subdf[c].dropna()
        # 대소문자 무시
        low_map = {c.lower(): c for c in subdf.columns}
        for c in ["close", "adj close"]:
            if c in low_map:
                return subdf[low_map[c]].dropna()
        # 마지막 수단: 수치형 첫 컬럼
        num_cols = subdf.select_dtypes(include="number").columns
        if len(num_cols):
            return subdf[num_cols[0]].dropna()
        return pd.Series(dtype=float)

    try:
        if not isinstance(df.columns, pd.MultiIndex):
            # ── Case D: 단일 Index ─────────────────────────────
            s = _pick_close(df)
            if not s.empty:
                s.name = ticker
                return s
            return pd.Series(dtype=float, name=ticker)

        # MultiIndex 처리
        lvl0 = df.columns.get_level_values(0).tolist()
        lvl1 = df.columns.get_level_values(1).tolist()
        lvl0_low = [str(x).lower() for x in lvl0]
        lvl1_low = [str(x).lower() for x in lvl1]
        t_up = ticker.upper()

        # ── Case A: level-0 = Price name ('Close' / 'Price' 등) ─
        #   최신 yfinance: columns = [('Close','AAPL'),('Volume','AAPL'),...]
        price_in_lvl0 = any(c in lvl0_low for c in ["close", "adj close"])
        if price_in_lvl0:
            for want in ["close", "adj close"]:
                indices = [i for i, v in enumerate(lvl0_low) if v == want]
                if not indices:
                    continue
                # level-1 값(ticker)으로 필터
                for i in indices:
                    l1_val = str(lvl1[i]).upper()
                    if l1_val == t_up or l1_val == "":
                        s = df.iloc[:, i].dropna()
                        if not s.empty:
                            s.name = ticker
                            return s
                # ticker가 level-1에 없으면 xs 시도
                actual_col = lvl0[indices[0]]
                try:
                    sub = df.xs(actual_col, axis=1, level=0, drop_level=True)
                    col_map = {str(c).upper(): c for c in sub.columns}
                    match = col_map.get(t_up) or col_map.get("") or (list(col_map.values())[0] if col_map else None)
                    if match is not None:
                        s = sub[match].dropna()
                        if not s.empty:
                            s.name = ticker
                            return s
                except Exception:
                    pass

        # ── Case B: level-0 = Ticker name ──────────────────────
        #   구버전: columns = [('AAPL','Close'),('AAPL','Volume'),...]
        ticker_in_lvl0 = any(str(x).upper() == t_up for x in lvl0)
        if ticker_in_lvl0:
            actual_t = next(x for x in lvl0 if str(x).upper() == t_up)
            try:
                sub = df.xs(actual_t, axis=1, level=0, drop_level=True)
                s = _pick_close(sub)
                if not s.empty:
                    s.name = ticker
                    return s
            except Exception:
                pass

        # ── Case C: level-1 = Price name ───────────────────────
        price_in_lvl1 = any(c in lvl1_low for c in ["close", "adj close"])
        if price_in_lvl1:
            for want in ["close", "adj close"]:
                indices = [i for i, v in enumerate(lvl1_low) if v == want]
                if not indices:
                    continue
                for i in indices:
                    l0_val = str(lvl0[i]).upper()
                    if l0_val == t_up or l0_val == "":
                        s = df.iloc[:, i].dropna()
                        if not s.empty:
                            s.name = ticker
                            return s
                actual_col = lvl1[indices[0]]
                try:
                    sub = df.xs(actual_col, axis=1, level=1, drop_level=True)
                    col_map = {str(c).upper(): c for c in sub.columns}
                    match = col_map.get(t_up) or (list(col_map.values())[0] if col_map else None)
                    if match is not None:
                        s = sub[match].dropna()
                        if not s.empty:
                            s.name = ticker
                            return s
                except Exception:
                    pass

        # ── 마지막 수단: 전체 수치형 컬럼 첫 번째 ───────────────
        num_cols = df.select_dtypes(include="number").columns
        if len(num_cols):
            s = df[num_cols[0]].dropna()
            if not s.empty:
                s.name = ticker
                dprint(f"  [추출 최후수단] {ticker}: 컬럼={num_cols[0]}")
                return s

    except Exception as e:
        dprint(f"  [추출 오류] {ticker}: {e}")

    return pd.Series(dtype=float, name=ticker)


def _get_close_from_hist(hist: pd.DataFrame, ticker: str) -> pd.Series:
    """
    yf.Ticker().history() 반환 DataFrame에서 Close 추출.
    최신 yfinance 2.x: hist.columns = MultiIndex([('Close', '005930.KS'), ...])
    구버전 yfinance   : hist.columns = ['Open','High','Low','Close', ...]
    """
    if hist is None or hist.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(hist.columns, pd.MultiIndex):
        return _extract_close_series(hist, ticker)
    # 단일 인덱스
    col_low = {str(c).lower(): c for c in hist.columns}
    for cname in ["close", "adj close"]:
        if cname in col_low:
            return hist[col_low[cname]].dropna().rename(ticker)
    # 수치형 첫 컬럼
    num_cols = hist.select_dtypes(include=[float, int]).columns
    if len(num_cols) > 0:
        return hist[num_cols[0]].dropna().rename(ticker)
    return pd.Series(dtype=float, name=ticker)


def _fdr_close(df_fdr: pd.DataFrame, ticker: str) -> pd.Series:
    """
    FinanceDataReader 결과에서 Close 추출.
    ─────────────────────────────────────────────────────────────
    FDR 버전별 컬럼명:
      - 구버전: ['Open','High','Low','Close','Volume','Change']
      - 신버전: ['Open','High','Low','Close','Adj Close','Volume']
      - 일부:   ['open','high','low','close',...]  (소문자)
    수치형 컬럼 fallback으로 버전 무관 동작 보장.
    ─────────────────────────────────────────────────────────────
    """
    if df_fdr is None or df_fdr.empty:
        return pd.Series(dtype=float, name=ticker)
    # 1) 이름 우선
    for col in ["Close", "Adj Close", "close", "adj close"]:
        if col in df_fdr.columns:
            s = df_fdr[col].dropna()
            if not s.empty and pd.api.types.is_numeric_dtype(s):
                s.name = ticker
                return s
    # 2) 대소문자 무시
    low_map = {c.lower(): c for c in df_fdr.columns}
    for key in ["close", "adj close"]:
        if key in low_map:
            s = df_fdr[low_map[key]].dropna()
            if not s.empty and pd.api.types.is_numeric_dtype(s):
                s.name = ticker
                return s
    # 3) 수치형 컬럼 중 'Volume'/'Change' 제외 후 첫 번째
    exclude = {"volume", "change", "거래량"}
    for col in df_fdr.columns:
        if col.lower() in exclude:
            continue
        s = df_fdr[col].dropna()
        if not s.empty and pd.api.types.is_numeric_dtype(s) and (s > 0).all():
            dprint(f"  [FDR fallback컬럼] {ticker}: '{col}'")
            s.name = ticker
            return s
    return pd.Series(dtype=float, name=ticker)


def _history_close(hist: pd.DataFrame, ticker: str) -> pd.Series:
    """
    yf.Ticker().history() 결과에서 Close 추출.
    ─────────────────────────────────────────────────────────────
    yfinance 버전별 history() 반환 구조:
      - 구버전 (≤0.2.30): 단순 DF, 컬럼=['Open','High','Low','Close',...]
      - 신버전 (≥0.2.31): MultiIndex DF 또는 단순 DF (auto_adjust 여부)
      - 일부 환경: 컬럼 튜플 ('Close','005930.KS') 형태
    ─────────────────────────────────────────────────────────────
    """
    if hist is None or hist.empty:
        return pd.Series(dtype=float, name=ticker)

    # MultiIndex면 _extract_close_series 위임
    if isinstance(hist.columns, pd.MultiIndex):
        return _extract_close_series(hist, ticker)

    # 단순 Index: 컬럼이 튜플인 경우 (일부 yfinance 버전)
    if hist.columns.dtype == object:
        for col in hist.columns:
            col_str = str(col).lower()
            if "close" in col_str or "adj" in col_str:
                s = hist[col].dropna()
                if not s.empty and pd.api.types.is_numeric_dtype(s):
                    s.name = ticker
                    return s

    # 일반 컬럼명 처리
    for col in ["Close", "Adj Close", "close", "adj close"]:
        if col in hist.columns:
            s = hist[col].dropna()
            if not s.empty:
                s.name = ticker
                return s

    # 수치형 첫 컬럼 fallback
    num_cols = hist.select_dtypes(include="number").columns
    exclude = {"volume", "dividends", "stock splits"}
    for col in num_cols:
        if col.lower() not in exclude:
            s = hist[col].dropna()
            if not s.empty and (s > 0).all():
                dprint(f"  [history fallback컬럼] {ticker}: '{col}'")
                s.name = ticker
                return s

    return pd.Series(dtype=float, name=ticker)


def _fetch_kr_ticker(ticker: str, start: str, end: str) -> pd.Series:
    """
    한국 종목 전용 fetcher.
    ─────────────────────────────────────────────────────────────
    우선순위:
      1차) FinanceDataReader  — KR 데이터 가장 안정적·빠름
      2차) yf.Ticker().history()  — FDR 실패 시
      3차) yf.download() 단일  — 최후 수단
    ─────────────────────────────────────────────────────────────
    모든 단계에서 repair=False (속도), auto_adjust=True (수정주가).
    컬럼 추출은 전용 헬퍼로 버전 무관 처리.
    ─────────────────────────────────────────────────────────────
    """
    code = ticker.split(".")[0]  # "005930.KS" → "005930"

    # ── 1차: FinanceDataReader ────────────────────────────────
    try:
        import FinanceDataReader as fdr
        t0 = time.time()
        df_fdr = fdr.DataReader(code, start, end)
        elapsed = time.time() - t0
        s = _fdr_close(df_fdr, ticker)
        if not s.empty:
            dprint(f"  [KR 1차 FDR] {ticker}({code}): {len(s)}일 ({elapsed:.1f}s)")
            return s
        dprint(f"  [KR 1차 FDR] {ticker} 빈 결과 ({elapsed:.1f}s)")
    except Exception as e:
        dprint(f"  [KR 1차 FDR] {ticker} 실패: {e}")

    # ── 2차: yf.Ticker().history() ───────────────────────────
    for attempt in range(3):
        try:
            t0 = time.time()
            hist = yf.Ticker(ticker).history(
                start=start, end=end,
                auto_adjust=True, actions=False, repair=False,
            )
            elapsed = time.time() - t0
            s = _history_close(hist, ticker)
            if not s.empty:
                dprint(f"  [KR 2차 history] {ticker}: {len(s)}일 ({elapsed:.1f}s, 시도{attempt+1})")
                return s
            dprint(f"  [KR 2차 history] {ticker} 빈 결과 ({elapsed:.1f}s, 시도{attempt+1})")
        except Exception as e:
            dprint(f"  [KR 2차 history] {ticker} 시도{attempt+1} 실패: {e}")
        time.sleep(0.5 * (attempt + 1))

    # ── 3차: yf.download() 단일 ───────────────────────────────
    for attempt in range(3):
        try:
            t0 = time.time()
            df = _yf_download_safe(ticker, start, end)
            elapsed = time.time() - t0
            s = _extract_close_series(df, ticker)
            if not s.empty:
                dprint(f"  [KR 3차 download] {ticker}: {len(s)}일 ({elapsed:.1f}s, 시도{attempt+1})")
                return s
            dprint(f"  [KR 3차 download] {ticker} 빈 결과 ({elapsed:.1f}s, 시도{attempt+1})")
        except Exception as e:
            dprint(f"  [KR 3차 download] {ticker} 시도{attempt+1} 실패: {e}")
        time.sleep(0.5 * (attempt + 1))

    dprint(f"  [KR] {ticker} 모든 방법 실패 → 빈 Series 반환")
    return pd.Series(dtype=float, name=ticker)


def _yf_download_safe(tickers_arg, start: str, end: str) -> pd.DataFrame:
    """
    yfinance 버전에 관계없이 안전하게 download() 호출.
    ─────────────────────────────────────────────────────────────
    yfinance 0.2.x: group_by, threads 파라미터 지원
    yfinance 0.2.31+: group_by deprecated, threads 제거됨
    → 두 파라미터 모두 제거한 단순 호출이 모든 버전에서 동작.
    ─────────────────────────────────────────────────────────────
    """
    # 공통 kwargs (버전 무관)
    kwargs = dict(
        start=start, end=end,
        auto_adjust=True,
        repair=False,
        progress=False,
    )
    # multi_level_index=False → 단일 종목도 MultiIndex 아닌 단순 DF 반환 (0.2.40+)
    # 지원 안 하는 버전은 TypeError → 무시
    try:
        return yf.download(tickers_arg, multi_level_index=True, **kwargs)
    except TypeError:
        pass
    try:
        return yf.download(tickers_arg, **kwargs)
    except Exception as e:
        dprint(f"  [download 실패] {e}")
        return pd.DataFrame()


def _fetch_us_batch(tickers: list, start: str, end: str) -> dict:
    """
    미국 종목 배치 다운로드 (속도 핵심).
    ─────────────────────────────────────────────────────────────
    설계:
    1) 2종목 이상 → yf.download(list) 1회 배치 호출 (속도 최우선)
    2) 배치 누락 종목 → 개별 download 재시도 (3회)
    3) group_by / threads 파라미터 완전 제거 (yfinance 2.x 대응)
    ─────────────────────────────────────────────────────────────
    """
    results: dict = {}
    missing: list = []

    # ── 단일 종목: 배치 없이 직접 다운로드 ───────────────────
    if len(tickers) == 1:
        t = tickers[0]
        t0 = time.time()
        try:
            df = _yf_download_safe(t, start, end)
            s = _extract_close_series(df, t)
            elapsed = time.time() - t0
            if not s.empty:
                dprint(f"  [US 단일] {t}: {len(s)}일 ({elapsed:.1f}s)")
                results[t] = s
                return results
            dprint(f"  [US 단일] {t}: 빈 결과 ({elapsed:.1f}s)")
        except Exception as e:
            dprint(f"  [US 단일 실패] {t}: {e}")
        results[t] = pd.Series(dtype=float, name=t)
        return results

    # ── 다수 종목: 배치 다운로드 ──────────────────────────────
    t0 = time.time()
    df = _yf_download_safe(tickers, start, end)
    elapsed = time.time() - t0

    if df is not None and not df.empty:
        dprint(f"  [US 배치] {len(tickers)}종목 완료 ({elapsed:.1f}s) columns={list(df.columns[:6])}")
        for t in tickers:
            s = _extract_close_series(df, t)
            if not s.empty:
                results[t] = s
                dprint(f"    ✓ {t}: {len(s)}일")
            else:
                missing.append(t)
                dprint(f"    ✗ {t}: 배치 추출 실패 → 개별 재시도")
    else:
        missing = list(tickers)
        dprint(f"  [US 배치] 전체 실패 ({elapsed:.1f}s) → 전 종목 개별 재시도")

    # ── 누락 종목 개별 재시도 ─────────────────────────────────
    for t in missing:
        t1 = time.time()
        fetched = False
        for attempt in range(3):
            try:
                df_single = _yf_download_safe(t, start, end)
                s = _extract_close_series(df_single, t)
                if not s.empty:
                    results[t] = s
                    elapsed = time.time() - t1
                    dprint(f"  [US 개별] {t}: {len(s)}일 ({elapsed:.1f}s, 시도{attempt+1})")
                    fetched = True
                    break
                dprint(f"  [US 개별] {t} 시도{attempt+1}: 빈 결과")
            except Exception as e:
                dprint(f"  [US 개별] {t} 시도{attempt+1} 실패: {e}")
            time.sleep(0.5 * (attempt + 1))  # 재시도 대기
        if not fetched:
            results[t] = pd.Series(dtype=float, name=t)
            dprint(f"  [US] {t}: 모든 방법 실패")

    return results


def fetch_all(tickers: list, start: str, end: str) -> dict:
    """
    메인 fetcher.
    캐시 → US 배치 / KR 개별 → 결과 저장 후 반환.
    """
    t_total = time.time()

    # ── 캐시 확인 ────────────────────────────────────────────
    key = _cache_key(tickers, start, end)
    with _cache_lock:
        if key in _PRICE_CACHE:
            dprint("[캐시 HIT] 즉시 반환")
            return _PRICE_CACHE[key]

    # ── US / KR 분리 ─────────────────────────────────────────
    kr_tickers = [t for t in tickers if t.endswith(".KS") or t.endswith(".KQ")]
    us_tickers = [t for t in tickers if t not in kr_tickers]

    dprint(f"[fetch_all 시작] US={us_tickers}, KR={kr_tickers}")

    results: dict = {}

    # ── 미국 배치 다운로드 ────────────────────────────────────
    if us_tickers:
        us_results = _fetch_us_batch(us_tickers, start, end)
        for t, s in us_results.items():
            if not s.empty:
                s.index = _safe_tz_strip(s.index)
                s = s.sort_index()
                results[t] = s.rename(t)
            else:
                results[t] = s

    # ── 한국 개별 다운로드 (KRW → USD 변환 포함) ─────────────
    for t in kr_tickers:
        s = _fetch_kr_ticker(t, start, end)
        if not s.empty:
            s.index = _safe_tz_strip(s.index)
            s = s.sort_index()
            s = s / 1500.0   # KRW → USD (1,500원 기준)
            results[t] = s.rename(t)
        else:
            results[t] = s

    ok  = sum(1 for v in results.values() if not v.empty)
    tot = len(tickers)
    elapsed = time.time() - t_total
    dprint(f"[fetch_all 완료] 총 {elapsed:.1f}s | 성공 {ok}/{tot} | KR={len(kr_tickers)}, US={len(us_tickers)}")

    # ── 캐시 저장 ────────────────────────────────────────────
    with _cache_lock:
        _PRICE_CACHE[key] = results

    return results


# ============================================================
# 백테스팅 엔진
# ============================================================
# [거치식]
#   - D0(시작일)에 총 원금 전액으로 주식 매수
#   - 보유 주수 = total_invest / P[0]  (고정)
#   - i일 평가금  = 보유주수 × P[i]
#   - 수익률(%)   = (평가금 / 원금 - 1) × 100
#
# [적립식]
#   - 매 거래일마다 (total_invest / 총 거래일수)씩 추가 매수
#   - 누적 투입 원금 = daily_invest × (i+1)
#   - 누적 보유 주수 = Σ (daily_invest / P[j])  for j=0..i
#   - i일 평가금    = 누적 보유 주수 × P[i]
#   - 수익률(%)     = (평가금 / 누적 원금 - 1) × 100
# ============================================================

def backtest_lump_sum(adj_close: np.ndarray, total_usd: float):
    """거치식: D0에 전액 매수."""
    p0 = adj_close[0]
    if p0 <= 0:
        raise ValueError("시작가가 0 이하입니다.")
    shares    = total_usd / p0
    portfolio = shares * adj_close
    invested  = np.full(len(adj_close), total_usd)
    roi       = (portfolio / total_usd - 1.0) * 100.0
    return portfolio, invested, roi


def backtest_dca(adj_close: np.ndarray, total_usd: float):
    """적립식(DCA): 매 거래일 동일 금액 매수."""
    n      = len(adj_close)
    daily  = total_usd / n
    shares_per_day = daily / adj_close
    cum_shares     = np.cumsum(shares_per_day)
    portfolio      = cum_shares * adj_close
    invested       = daily * np.arange(1, n + 1)
    roi            = (portfolio / invested - 1.0) * 100.0
    return portfolio, invested, roi


def run_backtest(ticker1, ticker2, ticker3,
                 krw_amount, from_date, to_date, strategy):
    """
    메인 백테스팅 함수.
    매 호출마다 새 Figure 생성 → 재실행 누적 버그 없음.
    """
    # ── 날짜 파싱 ─────────────────────────────────────────────
    def parse_date(val, fallback):
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        if isinstance(val, date):
            return val.strftime("%Y-%m-%d")
        s = str(val).strip()
        try:
            datetime.strptime(s[:10], "%Y-%m-%d")
            return s[:10]
        except Exception:
            return fallback

    today_str   = datetime.today().strftime("%Y-%m-%d")
    ten_ago_str = datetime.today().replace(
        year=datetime.today().year - 10
    ).strftime("%Y-%m-%d")

    start_date = parse_date(from_date, ten_ago_str)
    end_date   = parse_date(to_date,   today_str)

    if start_date >= end_date:
        return _error_fig("시작일이 종료일보다 같거나 늦습니다. 날짜를 확인하세요.")

    # ── 종목 해석 ─────────────────────────────────────────────
    raw_list = [ticker1, ticker2, ticker3]
    tickers, display_names = [], []
    for raw in raw_list:
        raw = str(raw).strip()
        if not raw:
            continue
        resolved = resolve_ticker(raw)
        tickers.append(resolved)
        display_names.append(raw)

    if not tickers:
        return _error_fig("종목을 하나 이상 입력해주세요.")

    total_usd = float(krw_amount) / 1500.0
    is_lump   = "거치식" in strategy

    # ── 데이터 다운로드 (속도 개선 fetch_all 호출) ────────────
    price_dict = fetch_all(tickers, start_date, end_date)

    # ── Figure 생성 ───────────────────────────────────────────
    fig = go.Figure()
    first_valid_index = None
    first_invested    = None

    for ticker, display_name in zip(tickers, display_names):
        series = price_dict.get(ticker, pd.Series(dtype=float))

        if series is None or series.empty:
            dprint(f"[스킵] 데이터 없음: {ticker}")
            continue

        series = series.sort_index().dropna()
        if len(series) < 2:
            dprint(f"[스킵] 데이터 부족: {ticker} ({len(series)}일)")
            continue

        idx    = series.index
        prices = series.values.astype(float)

        try:
            if is_lump:
                portfolio, invested, roi = backtest_lump_sum(prices, total_usd)
            else:
                portfolio, invested, roi = backtest_dca(prices, total_usd)
        except Exception as e:
            dprint(f"[계산 오류] {ticker}: {e}")
            continue

        if first_valid_index is None or len(idx) > len(first_valid_index):
            first_valid_index = idx
            first_invested    = invested

        final_val = portfolio[-1]
        final_roi = roi[-1]
        final_inv = invested[-1]

        custom = np.column_stack([roi, invested])

        fig.add_trace(go.Scatter(
            x=idx,
            y=portfolio,
            customdata=custom,
            mode="lines",
            name=(
                f"{display_name}  "
                f"최종 ${final_val:,.0f} "
                f"({final_roi:+,.1f}%)"
            ),
            hovertemplate=(
                "<b>%{x|%Y-%m-%d}</b><br>"
                "평가금: $%{y:,.2f}<br>"
                "수익률: %{customdata[0]:,.2f}%<br>"
                "투입원금: $%{customdata[1]:,.2f}"
                "<extra></extra>"
            ),
            line=dict(width=2.5),
        ))

    # ── 원금 기준선 ──────────────────────────────────────────
    if first_valid_index is not None and first_invested is not None:
        fig.add_trace(go.Scatter(
            x=first_valid_index,
            y=first_invested,
            mode="lines",
            name="투입 원금 (Principal)",
            line=dict(color="gray", width=1.8, dash="dash"),
            hovertemplate=(
                "<b>%{x|%Y-%m-%d}</b><br>"
                "누적 원금: $%{y:,.2f}"
                "<extra></extra>"
            ),
        ))

    if not fig.data:
        return _error_fig("유효한 데이터가 없습니다. 종목 코드와 날짜를 확인하세요.")

    # ── 레이아웃 ─────────────────────────────────────────────
    strategy_label = "거치식" if is_lump else "적립식"
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{start_date} ~ {end_date}  {strategy_label} 백테스팅</b>"
                f"<br><span style='font-size:13px;color:gray;'>"
                f"총 원금: {float(krw_amount):,.0f}원  "
                f"(환율 1,500원 기준 → ${total_usd:,.0f})</span>"
            ),
            font=dict(size=17),
        ),
        xaxis_title="날짜",
        yaxis_title="평가금액 (USD $)",
        hovermode="x unified",
        template="plotly_white",
        legend=dict(
            yanchor="top", y=0.99,
            xanchor="left", x=0.01,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="lightgray",
            borderwidth=1,
        ),
        margin=dict(t=100, b=60, l=60, r=40),
    )
    return fig


def _error_fig(msg: str) -> go.Figure:
    """에러 메시지용 빈 Figure."""
    fig = go.Figure()
    fig.update_layout(
        title=f"⚠️ {msg}",
        template="plotly_white",
    )
    return fig


# ============================================================
# Gradio UI
# ============================================================
TODAY   = datetime.today().strftime("%Y-%m-%d")
TEN_AGO = (datetime.today().replace(year=datetime.today().year - 10)
           .strftime("%Y-%m-%d"))

DATE_PICKER_HTML = """
<style>
  .dp-wrap { display:flex; gap:24px; align-items:flex-end; flex-wrap:wrap; }
  .dp-group { display:flex; flex-direction:column; gap:4px; }
  .dp-group label { font-size:14px; font-weight:600; color:#374151; }
  .dp-group input[type=date] {
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size:15px;
    cursor: pointer;
    background: white;
    color: #111827;
    min-width: 170px;
  }
  .dp-group input[type=date]:focus {
    outline: 2px solid #6366f1;
    border-color: transparent;
  }
</style>
<div class="dp-wrap">
  <div class="dp-group">
    <label>📅 시작일</label>
    <input type="date" id="dp_from" value="{FROM}" max="{TODAY}"
      onchange="document.querySelector('#tb_from textarea').value=this.value;
                document.querySelector('#tb_from textarea').dispatchEvent(new Event('input',{bubbles:true}));" />
  </div>
  <div class="dp-group">
    <label>📅 종료일</label>
    <input type="date" id="dp_to" value="{TODAY}" max="{TODAY}"
      onchange="document.querySelector('#tb_to textarea').value=this.value;
                document.querySelector('#tb_to textarea').dispatchEvent(new Event('input',{bubbles:true}));" />
  </div>
</div>
""".replace("{FROM}", TEN_AGO).replace("{TODAY}", TODAY)

with gr.Blocks(theme=gr.themes.Soft(), title="퀀트 백테스팅") as dashboard:
    gr.Markdown("## 📊 퀀트 백테스팅 대시보드")

    with gr.Row():
        t1 = gr.Textbox(label="종목 1", value="NVDA",      placeholder="예: 엔비디아 / NVDA")
        t2 = gr.Textbox(label="종목 2", value="삼성전자",  placeholder="예: 삼성전자 / 005930")
        t3 = gr.Textbox(label="종목 3", value="QLD",       placeholder="예: 나스닥2배 / QLD")

    with gr.Row():
        krw_input = gr.Number(
            label="총 투자금액 (원화 KRW)",
            value=100_000_000,
            step=1_000_000,
        )

    gr.Markdown("### 📅 투자 기간")
    gr.HTML(DATE_PICKER_HTML)

    with gr.Row():
        from_date_input = gr.Textbox(
            label="시작일 (YYYY-MM-DD) — 달력 또는 직접 입력",
            value=TEN_AGO,
            elem_id="tb_from",
            placeholder="예: 2015-01-02",
        )
        to_date_input = gr.Textbox(
            label="종료일 (YYYY-MM-DD) — 달력 또는 직접 입력",
            value=TODAY,
            elem_id="tb_to",
            placeholder="예: 2026-06-20",
        )

    strategy_input = gr.Radio(
        choices=["거치식 (첫날 전액 투자)", "적립식 (매일 분할 투자)"],
        value="거치식 (첫날 전액 투자)",
        label="투자 방식",
    )

    run_btn     = gr.Button("🚀 백테스팅 실행", variant="primary", size="lg")
    plot_output = gr.Plot(label="백테스팅 결과", show_label=False)

    run_btn.click(
        fn=run_backtest,
        inputs=[
            t1, t2, t3,
            krw_input,
            from_date_input,
            to_date_input,
            strategy_input,
        ],
        outputs=plot_output,
    )

# ── KRX 백그라운드 로드 ──────────────────────────────────────
threading.Thread(target=load_krx_map, daemon=True).start()

# ── 실행 ─────────────────────────────────────────────────────
import random
port = random.randint(7000, 7999)

dashboard.launch(
    debug=True,
    share=True,
    server_port=port,         # 매 실행마다 다른 포트 → 포트 충돌 방지
    prevent_thread_lock=True  # 코랩 환경 셀 블로킹 방지
)
