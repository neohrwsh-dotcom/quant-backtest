import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# ─── 페이지 기본 설정 ───
st.set_page_config(page_title="퀀트 백테스팅 대시보드", page_icon="📈", layout="wide")

# ─── 종목명 변환 사전 ───
DICT = {
    "애플": "AAPL", "마이크로소프트": "MSFT", "마소": "MSFT", "엔비디아": "NVDA", 
    "테슬라": "TSLA", "나스닥2배": "QLD", "나스닥3배": "TQQQ", "S&P500": "SPY",
    "삼성전자": "005930", "삼전": "005930", "SK하이닉스": "000660", "하이닉스": "000660",
    "LG에너지솔루션": "373220", "현대차": "005380", "에코프로비엠": "247540", "에코프로": "086520"
}

def get_real_ticker(raw):
    clean = raw.strip().replace(" ", "").upper()
    ticker = DICT.get(clean, clean)
    # 숫자로만 이루어진 짧은 입력값(예: '5930')을 6자리 '005930'으로 자동 보정
    if ticker.isdigit() and len(ticker) < 6:
        ticker = ticker.zfill(6)
    return ticker

# ─── UI 레이아웃 ───
st.title("📊 퀀트 백테스팅 대시보드")
st.markdown("해당 페이지는 특정 주식(ETF) 를 백테스팅하기 위해 개발되었습니다.")

col1, col2, col3 = st.columns(3)
t1_raw = col1.text_input("종목 1", "엔비디아", placeholder="예: 엔비디아, AAPL")
t2_raw = col2.text_input("종목 2", "5930", placeholder="예: 삼성전자, 5930")
t3_raw = col3.text_input("종목 3", "QLD", placeholder="예: QLD (비워도 됨)")

# 환율을 투자금 바로 옆으로 이동시켜 직관성을 높였습니다.
col_krw, col_fx, col_start, col_end = st.columns(4)
krw = col_krw.number_input("총 투자금액 (원화 KRW)", min_value=1000000, value=100000000, step=1000000)
fx = col_fx.number_input("환율 (1달러 당 원화)", min_value=500.0, value=1500.0, step=10.0)

start_date = col_start.date_input("시작일", value=datetime(2015, 1, 1), min_value=datetime(1980, 1, 1), max_value=datetime.today())
end_date = col_end.date_input("종료일", value=datetime.today(), min_value=datetime(1980, 1, 1), max_value=datetime.today())

col_strat, col_curr = st.columns(2)
strategy = col_strat.radio("투자 방식", ["거치식 (첫날 전액 투자)", "적립식 (매일 분할 투자)"], horizontal=True)
display_currency = col_curr.radio("표시 단위 선택", ["USD ($)", "KRW (₩)"], horizontal=True)

# ─── 백테스팅 엔진 ───
if st.button("🚀 백테스팅 실행", use_container_width=True):
    raw_inputs = [t for t in [t1_raw, t2_raw, t3_raw] if t.strip()]
    if not raw_inputs:
        st.error("종목을 하나 이상 입력해주세요.")
        st.stop()
        
    # 표시 통화에 따른 기본 원금 및 기호 세팅
    is_krw = "KRW" in display_currency
    curr_sym = "₩" if is_krw else "$"
    base_principal = krw if is_krw else (krw / fx)
    
    fig = go.Figure()
    summary_data = []
    has_data = False
    
    max_dates = None
    max_invested = None
    colors = ['#667eea', '#f6ad55', '#68d391']
    
    with st.spinner("데이터 수집 및 복리 계산 중..."):
        for i, raw in enumerate(raw_inputs):
            ticker = get_real_ticker(raw)
            try:
                # 1. 주가 데이터 로드
                if ticker.isdigit() and len(ticker) == 6:
                    df = fdr.DataReader(ticker, start_date, end_date)
                    if df.empty:
                        st.warning(f"{raw} ({ticker}) 데이터가 존재하지 않습니다.")
                        continue
                    series = df['Close'].dropna()
                else:
                    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                    if df.empty:
                        st.warning(f"{raw} ({ticker}) 데이터가 존재하지 않습니다.")
                        continue
                    if isinstance(df.columns, pd.MultiIndex):
                        series = df['Close'].iloc[:, 0].dropna()
                    else:
                        series = df['Close'].dropna()
                        
                if len(series) < 2:
                    continue
                    
                has_data = True
                
                # 2. 상장일 자동 인식 (데이터의 첫 날짜를 무조건 실제 시작일로 사용)
                actual_start_date = series.index[0]
                
                # 3. 전략별 계산
                if "거치식" in strategy:
                    # 거치식: 상장 첫날(또는 지정 시작일) 가격으로 전액 매수
                    p0 = series.iloc[0]
                    shares = base_principal / p0
                    portfolio = shares * series
                    invested = pd.Series(base_principal, index=series.index)
                else:
                    # 적립식: 총 원금을 '실제 영업일 수'로 나누어 매일 분할 매수
                    daily_principal = base_principal / len(series)
                    shares = (daily_principal / series).cumsum()
                    portfolio = shares * series
                    invested = pd.Series([daily_principal * (k + 1) for k in range(len(series))], index=series.index)
                    
                roi = (portfolio / invested - 1) * 100
                
                # 원금 기준선용 가장 긴 X축 저장
                if max_dates is None or len(series.index) > len(max_dates):
                    max_dates = series.index
                    max_invested = invested.values
                    
                final_val = portfolio.iloc[-1]
                final_roi = roi.iloc[-1]
                final_inv = invested.iloc[-1]
                
                # 4. 차트 렌더링 (통화 기호 적용)
                fig.add_trace(go.Scatter(
                    x=series.index, y=portfolio.values,
                    customdata=np.column_stack([roi.values, invested.values]),
                    mode='lines',
                    name=f"{raw}  {curr_sym}{final_val:,.0f} ({final_roi:+.1f}%)",
                    hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>평가금: {curr_sym}%{{y:,.0f}}<br>수익률: %{{customdata[0]:,.2f}}%<br>투입원금: {curr_sym}%{{customdata[1]:,.0f}}<extra></extra>",
                    line=dict(width=2.5, color=colors[i % len(colors)])
                ))
                
                # 요약 데이터 적재
                summary_data.append({
                    "종목": raw,
                    "실제 시작일(상장일)": actual_start_date.strftime("%Y-%m-%d"),
                    "투자기간": f"{len(series):,} 영업일",
                    "투입 원금": f"{curr_sym}{final_inv:,.0f}",
                    "최종 평가금": f"{curr_sym}{final_val:,.0f}",
                    "누적 수익률": f"{final_roi:+.2f}%"
                })
                
            except Exception as e:
                st.error(f"{raw} 처리 중 내부 에러 발생: {e}")
                
    # ─── 차트 및 요약 테이블 출력 ───
    if has_data:
        if max_dates is not None:
            fig.add_trace(go.Scatter(
                x=max_dates, y=max_invested,
                mode='lines', name='투입 원금 (Principal)',
                hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>누적 원금: {curr_sym}%{{y:,.0f}}<extra></extra>',
                line=dict(color='#a0aec0', width=1.8, dash='dash')
            ))
            
        fig.update_layout(
            hovermode='x unified',
            template='plotly_white',
            legend=dict(yanchor='top', y=0.99, xanchor='left', x=0.01, bgcolor='rgba(255,255,255,0.85)', bordercolor='#e2e8f0', borderwidth=1),
            margin=dict(t=40, b=40, l=40, r=40),
            yaxis_title=f"계좌 평가금액 ({display_currency})"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("📋 종목별 백테스팅 요약")
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
    else:
        st.error("그릴 수 있는 유효한 데이터가 없습니다. 날짜와 종목을 확인해주세요.")
