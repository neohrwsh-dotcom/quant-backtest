# ============================================================
# 퀀트 백테스팅 대시보드 v4 (버그픽스: 삼성전자/애플 데이터 누락 해결)
# 수정사항:
#   1. 달력 클릭 UI (JS date picker)
#   2. 설명 문구 제거
#   3. 거치식/적립식 수익률 계산 로직 완전 재작성 (정확도)
#   4. 재실행 버그 완전 수정 (포트 충돌, Plot 누적 등)
#   5. [속도 개선]
#      - yf.download() 배치 다운로드 (1회 요청으로 전 종목)
#      - repair=False (불필요한 추가 요청 제거)
#      - 메모리 캐시 (동일 종목·기간 재요청 즉시 반환)
#   6. [버그픽스 - 핵심]
#      - _safe_tz_strip(): tz-aware 인덱스에 tz_localize(None) 호출 → TypeError 수정
#        (yfinance는 UTC aware 인덱스를 반환 → tz_convert("UTC").tz_localize(None) 처리)
#      - _extract_close_series(): MultiIndex 컬럼 순서(Price×Ticker vs Ticker×Price)
#        모두 대응, 대소문자 무시 매칭 추가
#      - _per_ticker_fallback(): 배치에서 누락된 종목 자동 개별 재시도
#        (삼성전자, 애플 등 배치 누락 시에도 정상 데이터 반환)
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
# 속도 개선: 메모리 캐시 + yf.download() 배치 방식
# ============================================================

# 캐시 구조: { (tuple(sorted_tickers), start, end) : {ticker: pd.Series} }
_PRICE_CACHE: dict = {}
_cache_lock = threading.Lock()

def _cache_key(tickers: list, start: str, end: str) -> tuple:
    return (tuple(sorted(tickers)), start, end)

def _safe_tz_strip(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """
    timezone-aware / naive 어느 쪽이든 안전하게 tz-naive UTC로 변환.
    - tz 있으면 tz_convert("UTC").tz_localize(None)
    - tz 없으면 그대로
    """
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        return idx.tz_convert("UTC").tz_localize(None)
    return idx


def _extract_close_series(df: pd.DataFrame, ticker: str) -> pd.Series:
    """
    yfinance 반환 DataFrame에서 단일 ticker의 Close 시리즈를 안전하게 추출.
    MultiIndex / 단일 Index / 컬럼 순서 등 모든 케이스 대응.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)

    try:
        if isinstance(df.columns, pd.MultiIndex):
            lvl0 = df.columns.get_level_values(0).str.lower().tolist()
            lvl1 = df.columns.get_level_values(1).tolist()

            # Case A: (Price, Ticker) 순서 — 최신 yfinance 기본
            if "close" in lvl0:
                sub = df.xs("Close", axis=1, level=0, drop_level=True)
                if ticker in sub.columns:
                    return sub[ticker].dropna()
                # ticker 대소문자 무시 매칭
                col_map = {c.upper(): c for c in sub.columns}
                if ticker.upper() in col_map:
                    return sub[col_map[ticker.upper()]].dropna()

            # Case B: (Ticker, Price) 순서
            if ticker in lvl0 or ticker.upper() in [x.upper() for x in lvl0]:
                try:
                    sub = df.xs(ticker, axis=1, level=0, drop_level=True)
                    if "Close" in sub.columns:
                        return sub["Close"].dropna()
                    return sub.iloc[:, 0].dropna()
                except KeyError:
                    pass

            # Case C: "close" in lvl1 → (Ticker, Price) 순서로 level 바뀐 경우
            if "close" in [x.lower() for x in lvl1]:
                sub = df.xs("Close", axis=1, level=1, drop_level=True)
                if ticker in sub.columns:
                    return sub[ticker].dropna()
                col_map = {c.upper(): c for c in sub.columns}
                if ticker.upper() in col_map:
                    return sub[col_map[ticker.upper()]].dropna()

        else:
            # 단일 Index DataFrame
            if "Close" in df.columns:
                return df["Close"].dropna()
            # 대소문자 무시
            col_lower = {c.lower(): c for c in df.columns}
            if "close" in col_lower:
                return df[col_lower["close"]].dropna()
            return df.iloc[:, 0].dropna()

    except Exception as e:
        print(f"[추출 오류] {ticker}: {e}")

    return pd.Series(dtype=float, name=ticker)


def _per_ticker_fallback(ticker: str, start: str, end: str) -> pd.Series:
    """
    배치 다운로드에서 누락된 종목을 1개씩 재시도.
    repair=False 로 최대한 빠르게.
    """
    try:
        print(f"  [fallback] {ticker} 개별 다운로드 중...")
        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=True,
            repair=False,
            progress=False,
            timeout=30,
        )
        s = _extract_close_series(df, ticker)
        if s.empty:
            # Ticker.history() 로 한 번 더 시도
            hist = yf.Ticker(ticker).history(
                start=start, end=end,
                auto_adjust=True, repair=False
            )
            if not hist.empty and "Close" in hist.columns:
                s = hist["Close"].dropna()
                s.name = ticker
        return s
    except Exception as e:
        print(f"  [fallback 실패] {ticker}: {e}")
        return pd.Series(dtype=float, name=ticker)


def _batch_download(tickers: list, start: str, end: str) -> dict:
    """
    yf.download() 로 전 종목을 단일 HTTP 요청으로 받아옵니다.
    - auto_adjust=True  : 수정주가 (배당·분할 반영)
    - repair=False      : 추가 검증 요청 제거 → 속도 향상
    - progress=False    : tqdm 출력 억제

    ★ 핵심 수정사항
    1. _safe_tz_strip() : tz-aware/naive 상관없이 안전하게 tz 제거
    2. _extract_close_series() : MultiIndex 컬럼 순서 차이 완전 대응
    3. fallback : 배치에서 빈 종목은 개별 재시도
    반환: { ticker: pd.Series(Close) }
    """
    import time
    t0 = time.time()

    results: dict = {}
    missing: list = []

    # ── 1단계: 배치 다운로드 ────────────────────────────────
    try:
        df = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            repair=False,
            progress=False,
            threads=True,
            timeout=30,
        )
    except Exception as e:
        print(f"[배치 다운로드 실패] {e} → 전 종목 개별 fallback")
        df = None

    elapsed_batch = time.time() - t0
    print(f"[배치] {len(tickers)}종목 다운로드 완료 ({elapsed_batch:.1f}s)")

    if df is not None and not df.empty:
        for t in tickers:
            s = _extract_close_series(df, t)
            if s.empty:
                print(f"  [누락] {t} → fallback 예정")
                missing.append(t)
            else:
                # ★ tz-aware/naive 모두 안전하게 처리
                s.index = _safe_tz_strip(s.index)
                s = s.sort_index()
                if t.endswith(".KS") or t.endswith(".KQ"):
                    s = s / 1500.0
                results[t] = s.rename(t)
    else:
        missing = list(tickers)

    # ── 2단계: fallback (누락 종목 개별 재시도) ─────────────
    for t in missing:
        t1 = time.time()
        s = _per_ticker_fallback(t, start, end)
        if not s.empty:
            s.index = _safe_tz_strip(s.index)
            s = s.sort_index()
            if t.endswith(".KS") or t.endswith(".KQ"):
                s = s / 1500.0
            results[t] = s.rename(t)
            print(f"  [fallback 성공] {t} ({time.time()-t1:.1f}s, {len(s)}일)")
        else:
            results[t] = pd.Series(dtype=float, name=t)
            print(f"  [fallback 실패] {t} → 데이터 없음")

    print(f"[fetch 완료] 총 {time.time()-t0:.1f}s | 성공: {sum(1 for v in results.values() if not v.empty)}/{len(tickers)}")
    return results


def fetch_all(tickers: list, start: str, end: str) -> dict:
    """
    캐시 우선 → 미캐시 종목만 배치 다운로드.
    동일 종목·기간 재요청 시 0.1초 이하로 즉시 반환.
    """
    key = _cache_key(tickers, start, end)
    with _cache_lock:
        if key in _PRICE_CACHE:
            print("[캐시 HIT] 즉시 반환")
            return _PRICE_CACHE[key]

    # 캐시 미스 → 배치 다운로드
    results = _batch_download(tickers, start, end)

    with _cache_lock:
        _PRICE_CACHE[key] = results

    return results


# ============================================================
# 백테스팅 엔진 (핵심 로직 완전 재작성)
# ============================================================
#
# [거치식]
#   - D0(시작일)에 총 원금 전액으로 주식 매수
#   - 보유 주수 = total_invest / P[0]  (고정)
#   - i일 평가금  = 보유주수 × P[i]
#   - 수익률(%)   = (평가금 / 원금 - 1) × 100
#   ※ 이 구조가 곧 복리: 주가 상승분이 그대로 평가금에 반영됨
#
# [적립식]
#   - 매 거래일마다 (total_invest / 총 거래일수)씩 추가 매수
#   - 누적 투입 원금 = daily_invest × (i+1)
#   - 누적 보유 주수 = Σ (daily_invest / P[j])  for j=0..i
#   - i일 평가금    = 누적 보유 주수 × P[i]
#   - 수익률(%)     = (평가금 / 누적 원금 - 1) × 100
#   ※ 각 날 투입한 금액이 해당일 종가로 주식을 사고,
#      이후 주가 변동에 따라 복리처럼 증식됨
#
# ============================================================
def backtest_lump_sum(adj_close: np.ndarray, total_usd: float):
    """거치식: D0에 전액 매수."""
    p0 = adj_close[0]
    if p0 <= 0:
        raise ValueError("시작가가 0 이하입니다.")
    shares = total_usd / p0               # 매수 주수 (고정)
    portfolio = shares * adj_close        # 매일 평가금
    invested  = np.full(len(adj_close), total_usd)
    roi       = (portfolio / total_usd - 1.0) * 100.0
    return portfolio, invested, roi


def backtest_dca(adj_close: np.ndarray, total_usd: float):
    """
    적립식(DCA): 매 거래일 동일 금액 매수.
    daily_invest = total_usd / 총_거래일수
    """
    n = len(adj_close)
    daily = total_usd / n

    # 각 날 매수 주수
    shares_per_day = daily / adj_close          # shape (n,)

    # i일까지 누적 보유 주수 (cumsum)
    cum_shares = np.cumsum(shares_per_day)      # shape (n,)

    # i일 평가금
    portfolio = cum_shares * adj_close          # shape (n,)

    # 누적 투입 원금: 1일차=daily, 2일차=2*daily, ...
    invested = daily * np.arange(1, n + 1)     # shape (n,)

    roi = (portfolio / invested - 1.0) * 100.0
    return portfolio, invested, roi


def run_backtest(ticker1, ticker2, ticker3,
                 krw_amount, from_date, to_date, strategy):
    """
    메인 백테스팅 함수.
    매 호출마다 새 Figure를 생성하므로 재실행 버그 없음.
    """
    # ── 날짜 파싱 ─────────────────────────────────────────────
    def parse_date(val, fallback):
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        if isinstance(val, date):
            return val.strftime("%Y-%m-%d")
        s = str(val).strip()
        # YYYY-MM-DD 형식 검증
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

    # 날짜 순서 보정
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

    # ── 병렬 데이터 다운로드 ─────────────────────────────────
    price_dict = fetch_all(tickers, start_date, end_date)

    # ── Figure 생성 (★ 매 호출마다 새로 생성 → 재실행 버그 방지) ─
    fig = go.Figure()
    first_valid_index = None

    for ticker, display_name in zip(tickers, display_names):
        series = price_dict.get(ticker, pd.Series(dtype=float))

        if series is None or series.empty:
            print(f"[스킵] 데이터 없음: {ticker}")
            continue

        # 결측치 제거 + 인덱스 정렬
        series = series.sort_index().dropna()
        if len(series) < 2:
            print(f"[스킵] 데이터 부족: {ticker} ({len(series)}일)")
            continue

        idx    = series.index
        prices = series.values.astype(float)

        # ── 전략 분기 ──────────────────────────────────────────
        try:
            if is_lump:
                portfolio, invested, roi = backtest_lump_sum(prices, total_usd)
            else:
                portfolio, invested, roi = backtest_dca(prices, total_usd)
        except Exception as e:
            print(f"[계산 오류] {ticker}: {e}")
            continue

        # 최장 인덱스 기록 (원금선 그릴 때 사용)
        if first_valid_index is None or len(idx) > len(first_valid_index):
            first_valid_index = idx
            first_is_lump     = is_lump
            first_portfolio   = portfolio
            first_invested    = invested

        final_val = portfolio[-1]
        final_roi = roi[-1]
        final_inv = invested[-1]

        # hover용 customdata: [[roi, invested], ...]
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
    if first_valid_index is not None:
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

# ── 달력 선택 JavaScript (gr.HTML + input[type=date]) ────────
# Gradio 자체 달력 컴포넌트(gr.DateTime)는 버전에 따라 미지원일 수 있으므로
# HTML date picker를 직접 삽입하고, 변경 시 숨겨진 Textbox를 갱신하는 방식 사용.

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

# ── UI 구성 ──────────────────────────────────────────────────
with gr.Blocks(theme=gr.themes.Soft(), title="퀀트 백테스팅") as dashboard:
    gr.Markdown("## 📊 퀀트 백테스팅 대시보드")

    # 종목 입력
    with gr.Row():
        t1 = gr.Textbox(label="종목 1", value="엔비디아",   placeholder="예: 엔비디아 / NVDA")
        t2 = gr.Textbox(label="종목 2", value="삼성전자",   placeholder="예: 삼성전자 / 005930")
        t3 = gr.Textbox(label="종목 3", value="나스닥2배",  placeholder="예: 나스닥2배 / QLD")

    # 투자금액
    with gr.Row():
        krw_input = gr.Number(
            label="총 투자금액 (원화 KRW)",
            value=100_000_000,
            step=1_000_000,
        )

    # 📅 투자 기간 : 달력 클릭 UI + 텍스트 직접 입력 동시 지원
    gr.Markdown("### 📅 투자 기간")
    gr.HTML(DATE_PICKER_HTML)          # 달력 클릭 UI

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

    # 전략 선택
    strategy_input = gr.Radio(
        choices=["거치식 (첫날 전액 투자)", "적립식 (매일 분할 투자)"],
        value="거치식 (첫날 전액 투자)",
        label="투자 방식",
    )

    run_btn     = gr.Button("🚀 백테스팅 실행", variant="primary", size="lg")

    # ★ Plot 컴포넌트: show_label=False, container=False 로 깔끔하게
    # ★ 매 실행마다 새 Figure 객체를 반환하므로 누적 버그 없음
    plot_output = gr.Plot(label="백테스팅 결과", show_label=False)

    # ── 이벤트 연결 ──────────────────────────────────────────
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

# ── 실행 (Google Colab) ──────────────────────────────────────
# inline=True  → 코랩 셀 내 직접 렌더
# share=True   → 외부 공유 링크
# server_port  → 재실행 충돌 방지: 랜덤 포트 사용
import random
port = random.randint(7000, 7999)

dashboard.launch(
    debug=True,
    share=True,
    server_port=port,        # ★ 매 실행마다 다른 포트 → 포트 충돌 방지
    prevent_thread_lock=True # ★ 코랩 환경에서 셀 블로킹 방지
)
