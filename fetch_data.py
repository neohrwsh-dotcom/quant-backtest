# ============================================================
# 퀀트 백테스팅 대시보드 v5
# ─────────────────────────────────────────────────────────────
# 버그픽스 (v3→v5):
#   [핵심 1] _extract_close_series 완전 재작성
#            - 최신 yfinance(0.2.50+) MultiIndex(Price,Ticker) 구조 대응
#            - 컬럼 인덱스 직접 순회 방식으로 xs() 의존 제거
#            - KR 티커(005930.KS 등) MultiIndex 에서도 정확히 추출
#   [핵심 2] _fetch_kr_ticker 수정
#            - yf.Ticker().history() 반환값이 MultiIndex인 경우도 처리
#            - "Close" in hist.columns → _extract_close_series() 사용으로 교체
#   [핵심 3] _fetch_us_batch 수정
#            - 단일 ticker 개별 재시도 시에도 _extract_close_series() 일관 적용
#   [속도 유지]
#            - yf.download() 배치 (threads=True, repair=False)
#            - 인메모리 캐시 (_PRICE_CACHE)
#            - 미국/한국 분리 전략 유지
# ============================================================

# ── 패키지 설치 ─────────────────────────────────────────────
import subprocess, sys

def pip_install(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])

pip_install("yfinance", "gradio", "plotly", "finance-datareader")

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
    "아이온큐": "IONQ", "리게티": "RGTI", "ARM홀딩스": "ARM",
    "소파이": "SOFI", "로빈후드": "HOOD",
    "버크셔": "BRK-B", "JP모건": "JPM", "뱅크오브아메리카": "BAC",
    "골드만삭스": "GS", "비자": "V", "마스터카드": "MA",
    "존슨앤존슨": "JNJ", "화이자": "PFE", "머크": "MRK",
    "엑슨모빌": "XOM", "쉐브론": "CVX",
    "ASML": "ASML", "TSMC": "TSM", "ARM": "ARM",
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
_KRX_MAP: dict = {}
_krx_lock = threading.Lock()

def load_krx_map() -> dict:
    global _KRX_MAP
    with _krx_lock:
        if _KRX_MAP:
            return _KRX_MAP
        try:
            import FinanceDataReader as fdr
            ks = fdr.StockListing("KRX")
            result = {}
            for _, row in ks.iterrows():
                code   = str(row.get("Code",   "")).strip()
                name   = str(row.get("Name",   "")).strip()
                market = str(row.get("Market", "")).upper()
                if not code or not name:
                    continue
                suffix = ".KQ" if market == "KOSDAQ" else ".KS"
                yf_ticker = f"{code}{suffix}"
                result[name] = yf_ticker
                result[code] = yf_ticker
            _KRX_MAP = result
            print(f"[KRX 로드 완료] {len(result):,}개 매핑")
        except Exception as e:
            print(f"[KRX 로드 실패 - 내장 사전만 사용]: {e}")
            _KRX_MAP = {}
    return _KRX_MAP


def resolve_ticker(raw: str) -> str:
    """
    한글명 / 종목코드 / 영문티커 → yfinance 티커로 변환.
    우선순위: 내장 사전 → KRX 동적 사전 → 숫자 6자리 → 대문자 그대로
    """
    t = raw.strip().replace(" ", "")
    t_upper = t.upper()
    # 1) 내장 사전 (한글 포함)
    if t in BASE_NAME_TO_TICKER:
        return BASE_NAME_TO_TICKER[t]
    if t_upper in BASE_NAME_TO_TICKER:
        return BASE_NAME_TO_TICKER[t_upper]
    # 2) KRX 동적 사전
    krx = load_krx_map()
    if t in krx:
        return krx[t]
    if t_upper in krx:
        return krx[t_upper]
    # 3) 숫자 6자리 → KS
    if t.isdigit() and len(t) == 6:
        return t + ".KS"
    # 4) 원본 대문자 반환
    return t_upper


# ============================================================
# ★ 핵심 수정: _extract_close_series (v5 완전 재작성)
# ─────────────────────────────────────────────────────────────
# 문제: 기존 xs() 기반 방식이 최신 yfinance(0.2.50+)에서
#       MultiIndex 구조 변화로 인해 KR/US 모두 추출 실패
# 해결: 컬럼 인덱스를 직접 순회하여 (Price,Ticker) / (Ticker,Price)
#       두 가지 레이아웃 모두 안전하게 처리
# ============================================================
def _extract_close_series(df: pd.DataFrame, ticker: str) -> pd.Series:
    """
    yfinance DataFrame에서 Close 시리즈 추출.
    - flat DataFrame (단일 ticker / 구버전)
    - MultiIndex (Price, Ticker) → 최신 yfinance 기본
    - MultiIndex (Ticker, Price) → 구버전 yfinance
    모두 대응. xs() 사용 금지 (버전별 불안정).
    """
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)

    try:
        # ── Flat DataFrame ────────────────────────────────────
        if not isinstance(df.columns, pd.MultiIndex):
            cols_low = {str(c).lower(): str(c) for c in df.columns}
            for key in ["close", "adj close"]:
                if key in cols_low:
                    return df[cols_low[key]].dropna().rename(ticker)
            # 숫자 컬럼 첫 번째
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if num_cols:
                return df[num_cols[0]].dropna().rename(ticker)
            return pd.Series(dtype=float, name=ticker)

        # ── MultiIndex: 컬럼 직접 순회 ────────────────────────
        lvl0 = [str(x) for x in df.columns.get_level_values(0)]
        lvl1 = [str(x) for x in df.columns.get_level_values(1)]
        lvl0_low = [x.lower() for x in lvl0]
        lvl1_low = [x.lower() for x in lvl1]
        lvl0_up  = [x.upper() for x in lvl0]
        lvl1_up  = [x.upper() for x in lvl1]
        ticker_up = ticker.upper()

        # Case A: (Price, Ticker) → level0=Price명, level1=Ticker명
        # 최신 yfinance 기본 레이아웃
        if any(x in lvl0_low for x in ["close", "adj close"]):
            for price_key in ["close", "adj close"]:
                for col_idx, (p, t_col) in enumerate(zip(lvl0_low, lvl1_up)):
                    if p == price_key and t_col == ticker_up:
                        return df.iloc[:, col_idx].dropna().rename(ticker)

        # Case B: (Ticker, Price) → level0=Ticker명, level1=Price명
        if ticker_up in lvl0_up:
            for price_key in ["close", "adj close"]:
                for col_idx, (t_col, p) in enumerate(zip(lvl0_up, lvl1_low)):
                    if t_col == ticker_up and p == price_key:
                        return df.iloc[:, col_idx].dropna().rename(ticker)
            # price 컬럼 못 찾으면 해당 ticker의 첫 컬럼
            for col_idx, t_col in enumerate(lvl0_up):
                if t_col == ticker_up:
                    return df.iloc[:, col_idx].dropna().rename(ticker)

        # Case C: level1에 Price, level0에 Ticker (드문 경우)
        if ticker_up in lvl1_up:
            for price_key in ["close", "adj close"]:
                for col_idx, (t_col, p) in enumerate(zip(lvl1_up, lvl0_low)):
                    if t_col == ticker_up and p == price_key:
                        return df.iloc[:, col_idx].dropna().rename(ticker)

    except Exception as e:
        print(f"  [추출 오류] {ticker}: {e}")

    return pd.Series(dtype=float, name=ticker)


# ============================================================
# 데이터 다운로드: 캐시 + 미국 배치 / 한국 개별 분리 전략
# ============================================================
_PRICE_CACHE: dict = {}
_cache_lock  = threading.Lock()


def _cache_key(tickers: list, start: str, end: str) -> tuple:
    return (tuple(sorted(tickers)), start, end)


def _safe_tz_strip(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """tz-aware/naive 상관없이 tz-naive로 변환."""
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        return idx.tz_convert("UTC").tz_localize(None)
    return idx


# ─────────────────────────────────────────────────────────────
# ★ 핵심 수정: _fetch_kr_ticker (v5)
# 문제: yf.Ticker().history() 반환값이 최신 yfinance에서
#       MultiIndex DataFrame이거나 "Close" 컬럼 구조가 달라
#       "Close" in hist.columns 조건이 False가 되어 항상 실패
# 해결: _extract_close_series()로 일관되게 추출
# ─────────────────────────────────────────────────────────────
def _fetch_kr_ticker(ticker: str, start: str, end: str) -> pd.Series:
    """
    한국 종목 전용 fetcher.
    1차: yf.Ticker().history()  — _extract_close_series()로 추출 (버그픽스)
    2차: yf.download() 단일
    3차: FinanceDataReader fallback
    각 단계 최대 2회 재시도.
    """
    code = ticker.split(".")[0]  # "005930.KS" → "005930"

    # ── 1차: Ticker.history() ─────────────────────────────────
    for attempt in range(2):
        try:
            hist = yf.Ticker(ticker).history(
                start=start, end=end,
                auto_adjust=True, actions=False,
                timeout=20,
            )
            if hist is not None and not hist.empty:
                # ★ v5 핵심 수정: _extract_close_series() 사용
                s = _extract_close_series(hist, ticker)
                if s.empty:
                    # flat DataFrame에서 Close 직접 시도
                    if "Close" in hist.columns:
                        s = hist["Close"].dropna().rename(ticker)
                if not s.empty:
                    print(f"  [KR Ticker.history] {ticker} 성공 ({len(s)}일, 시도{attempt+1})")
                    return s
        except Exception as e:
            print(f"  [KR Ticker.history] {ticker} 시도{attempt+1} 실패: {e}")

    # ── 2차: yf.download() 단일 ──────────────────────────────
    for attempt in range(2):
        try:
            df = yf.download(
                ticker, start=start, end=end,
                auto_adjust=True, repair=False,
                progress=False, timeout=25,
            )
            s = _extract_close_series(df, ticker)
            if not s.empty:
                print(f"  [KR download] {ticker} 성공 ({len(s)}일, 시도{attempt+1})")
                return s
        except Exception as e:
            print(f"  [KR download] {ticker} 시도{attempt+1} 실패: {e}")

    # ── 3차: FinanceDataReader fallback ──────────────────────
    try:
        import FinanceDataReader as fdr
        df_fdr = fdr.DataReader(code, start, end)
        if df_fdr is not None and not df_fdr.empty:
            cols_low = {str(c).lower(): str(c) for c in df_fdr.columns}
            for key in ["close", "adj close"]:
                if key in cols_low:
                    s = df_fdr[cols_low[key]].dropna().rename(ticker)
                    print(f"  [KR FDR] {ticker} 성공 ({len(s)}일)")
                    return s
    except Exception as e:
        print(f"  [KR FDR] {ticker} 실패: {e}")

    print(f"  [KR] {ticker} 모든 방법 실패 → 빈 Series 반환")
    return pd.Series(dtype=float, name=ticker)


def _fetch_us_batch(tickers: list, start: str, end: str) -> dict:
    """
    미국 종목 배치 다운로드.
    배치에서 누락된 종목은 개별 재시도 (Ticker.history 포함).
    """
    t0 = time.time()
    results: dict = {}
    missing: list = []

    # ── 배치 다운로드 ─────────────────────────────────────────
    try:
        df = yf.download(
            tickers, start=start, end=end,
            auto_adjust=True, repair=False,
            progress=False, threads=True, timeout=30,
        )
    except Exception as e:
        print(f"  [US 배치 실패] {e}")
        df = None

    print(f"  [US 배치] {len(tickers)}종목 ({time.time()-t0:.1f}s)")

    if df is not None and not df.empty:
        for t in tickers:
            s = _extract_close_series(df, t)
            if not s.empty:
                results[t] = s
            else:
                missing.append(t)
    else:
        missing = list(tickers)

    # ── 누락 종목 개별 재시도 ─────────────────────────────────
    for t in missing:
        fetched = False
        # 1) yf.download 단일
        for attempt in range(2):
            try:
                df_single = yf.download(
                    t, start=start, end=end,
                    auto_adjust=True, repair=False,
                    progress=False, timeout=20,
                )
                s = _extract_close_series(df_single, t)
                if not s.empty:
                    results[t] = s
                    print(f"  [US download 단일] {t} 성공 ({len(s)}일, 시도{attempt+1})")
                    fetched = True
                    break
            except Exception as e:
                print(f"  [US download 단일] {t} 시도{attempt+1} 실패: {e}")

        # 2) yf.Ticker().history() fallback
        if not fetched:
            try:
                hist = yf.Ticker(t).history(
                    start=start, end=end,
                    auto_adjust=True, actions=False, timeout=20,
                )
                if hist is not None and not hist.empty:
                    s = _extract_close_series(hist, t)
                    if s.empty and "Close" in hist.columns:
                        s = hist["Close"].dropna().rename(t)
                    if not s.empty:
                        results[t] = s
                        print(f"  [US Ticker.history] {t} 성공 ({len(s)}일)")
                        fetched = True
            except Exception as e:
                print(f"  [US Ticker.history] {t} 실패: {e}")

        if not fetched:
            results[t] = pd.Series(dtype=float, name=t)
            print(f"  [US] {t} 모든 방법 실패")

    return results


def fetch_all(tickers: list, start: str, end: str) -> dict:
    """
    메인 fetcher: 캐시 → 미국 배치 / 한국 개별 분리 처리.
    동일 종목·기간 재요청은 캐시에서 즉시 반환.
    """
    t0 = time.time()

    key = _cache_key(tickers, start, end)
    with _cache_lock:
        if key in _PRICE_CACHE:
            print("[캐시 HIT] 즉시 반환")
            return _PRICE_CACHE[key]

    # 미국 / 한국 분리
    kr_tickers = [t for t in tickers if t.upper().endswith(".KS") or t.upper().endswith(".KQ")]
    us_tickers = [t for t in tickers if t not in kr_tickers]

    results: dict = {}

    # ── 미국 배치 ─────────────────────────────────────────────
    if us_tickers:
        us_results = _fetch_us_batch(us_tickers, start, end)
        for t, s in us_results.items():
            if not s.empty:
                s = s.copy()
                s.index = _safe_tz_strip(s.index)
                s = s.sort_index()
                results[t] = s.rename(t)
            else:
                results[t] = s

    # ── 한국 개별 ─────────────────────────────────────────────
    for t in kr_tickers:
        s = _fetch_kr_ticker(t, start, end)
        if not s.empty:
            s = s.copy()
            s.index = _safe_tz_strip(s.index)
            s = s.sort_index()
            # KRW → USD 변환 (환율 1,500 고정)
            s = s / 1500.0
            results[t] = s.rename(t)
        else:
            results[t] = s

    ok  = sum(1 for v in results.values() if not v.empty)
    tot = len(tickers)
    print(f"[fetch_all 완료] {time.time()-t0:.1f}s | 성공 {ok}/{tot} | KR={len(kr_tickers)}, US={len(us_tickers)}")

    with _cache_lock:
        _PRICE_CACHE[key] = results

    return results


# ============================================================
# 백테스팅 엔진
# ============================================================
# [거치식]
#   - D0(시작일)에 총 원금 전액으로 주식 매수
#   - 보유 주수 = total_usd / P[0]  (고정)
#   - i일 평가금 = 보유주수 × P[i]
#   - 수익률(%) = (평가금 / 원금 - 1) × 100
#
# [적립식]
#   - 매 거래일마다 (total_usd / 총_거래일수)씩 추가 매수
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
    n          = len(adj_close)
    daily      = total_usd / n
    cum_shares = np.cumsum(daily / adj_close)
    portfolio  = cum_shares * adj_close
    invested   = daily * np.arange(1, n + 1)
    roi        = (portfolio / invested - 1.0) * 100.0
    return portfolio, invested, roi


def run_backtest(ticker1, ticker2, ticker3,
                 krw_amount, from_date, to_date, strategy):
    """메인 백테스팅 함수."""

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

    # ── 데이터 다운로드 ──────────────────────────────────────
    price_dict = fetch_all(tickers, start_date, end_date)

    # ── Figure 생성 ──────────────────────────────────────────
    fig = go.Figure()
    first_valid_index = None
    first_invested    = None

    for ticker, display_name in zip(tickers, display_names):
        series = price_dict.get(ticker, pd.Series(dtype=float))

        if series is None or series.empty:
            print(f"[스킵] 데이터 없음: {ticker} (입력: {display_name})")
            continue

        series = series.sort_index().dropna()
        if len(series) < 2:
            print(f"[스킵] 데이터 부족: {ticker} ({len(series)}일)")
            continue

        idx    = series.index
        prices = series.values.astype(float)

        try:
            if is_lump:
                portfolio, invested, roi = backtest_lump_sum(prices, total_usd)
            else:
                portfolio, invested, roi = backtest_dca(prices, total_usd)
        except Exception as e:
            print(f"[계산 오류] {ticker}: {e}")
            continue

        if first_valid_index is None or len(idx) > len(first_valid_index):
            first_valid_index = idx
            first_invested    = invested

        final_val = portfolio[-1]
        final_roi = roi[-1]
        custom    = np.column_stack([roi, invested])

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
    gr.Markdown("## 📊 퀀트 백테스팅 대시보드 v5")

    with gr.Row():
        t1 = gr.Textbox(label="종목 1", value="엔비디아",  placeholder="예: 엔비디아 / NVDA / 005930")
        t2 = gr.Textbox(label="종목 2", value="삼성전자",  placeholder="예: 삼성전자 / 삼전 / 005930")
        t3 = gr.Textbox(label="종목 3", value="나스닥2배", placeholder="예: 나스닥2배 / QLD / TQQQ")

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
        inputs=[t1, t2, t3, krw_input, from_date_input, to_date_input, strategy_input],
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
    server_port=port,
    prevent_thread_lock=True,
)
