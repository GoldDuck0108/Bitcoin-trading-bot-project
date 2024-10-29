import os
from dotenv import load_dotenv
import pyupbit
import pandas as pd
import json
from openai import OpenAI
import ta
from ta.utils import dropna
import time
import requests
import base64
from PIL import Image
import io
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, WebDriverException, NoSuchElementException
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from pydantic import BaseModel
import sqlite3
from datetime import datetime, timedelta
import schedule

################################################################################
# 기본 설정
################################################################################

# .env 파일의 환경 변수 로드
load_dotenv()

# 로깅 설정 - INFO 레벨로 설정하여 주요 정보를 콘솔에 출력
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Upbit API 연결 설정
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
if not access or not secret:
    logger.error("API 키를 찾을 수 없습니다. .env 파일을 확인해주세요.")
    raise ValueError("API 키가 없습니다. .env 파일을 확인해주세요.")
upbit = pyupbit.Upbit(access, secret)

################################################################################
# 데이터 모델 및 데이터베이스 관련
################################################################################

class TradingDecision(BaseModel):
    """AI의 거래 결정을 저장할 데이터 모델"""
    decision: str  # 결정: 매수/매도/홀딩
    percentage: int  # 거래 비율 (%)
    reason: str  # 결정 이유

def init_db():
    """데이터베이스 연결 및 거래 내역 테이블 생성"""
    conn = sqlite3.connect('bitcoin_trades.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,          -- 거래 시간
                  decision TEXT,           -- 거래 결정 (매수/매도/홀딩)
                  percentage INTEGER,      -- 거래 비율
                  reason TEXT,            -- 거래 이유
                  btc_balance REAL,       -- BTC 잔고
                  krw_balance REAL,       -- KRW 잔고
                  btc_avg_buy_price REAL, -- BTC 평균 매수가
                  btc_krw_price REAL,     -- 현재 BTC 가격
                  reflection TEXT)         -- AI의 분석 및 반성
                ''')
    conn.commit()
    return conn

def log_trade(conn, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection=''):
    """거래 기록을 데이터베이스에 저장"""
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection))
    conn.commit()

def get_recent_trades(conn, days=7):
    """최근 거래 내역 조회"""
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
    c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (seven_days_ago,))
    columns = [column[0] for column in c.description]
    return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)

################################################################################
# 기술적 분석 및 데이터 수집
################################################################################

def add_indicators(df):
    """주어진 데이터프레임에 기술적 지표들을 추가"""
    # 볼린저 밴드 (20일 기준)
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()
    
    # RSI (14일 기준)
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    
    # MACD
    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    # 이동평균선
    df['sma_20'] = ta.trend.SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['ema_12'] = ta.trend.EMAIndicator(close=df['close'], window=12).ema_indicator()
    
    return df

def calculate_performance(trades_df):
    """투자 성과 계산 (수익률)"""
    if trades_df.empty:
        return 0
    initial_balance = trades_df.iloc[-1]['krw_balance'] + trades_df.iloc[-1]['btc_balance'] * trades_df.iloc[-1]['btc_krw_price']
    final_balance = trades_df.iloc[0]['krw_balance'] + trades_df.iloc[0]['btc_balance'] * trades_df.iloc[0]['btc_krw_price']
    return (final_balance - initial_balance) / initial_balance * 100

################################################################################
# 외부 API 데이터 수집
################################################################################

def get_fear_and_greed_index():
    """공포 탐욕 지수 조회"""
    url = "https://api.alternative.me/fng/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['data'][0]
    except requests.exceptions.RequestException as e:
        logger.error(f"공포 탐욕 지수 조회 중 오류 발생: {e}")
        return None

def get_bitcoin_news():
    """비트코인 관련 최신 뉴스 수집"""
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        logger.error("SERPAPI API 키가 없습니다.")
        return None
    
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_news",
        "q": "btc",
        "api_key": serpapi_key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        news_results = data.get("news_results", [])
        return [{
            "title": item.get("title", ""),
            "date": item.get("date", "")
        } for item in news_results[:5]]
    except requests.RequestException as e:
        logger.error(f"뉴스 데이터 수집 중 오류 발생: {e}")
        return []

################################################################################
# 차트 캡처 관련 (Selenium)
################################################################################

def create_driver():
    """크롬 드라이버 생성"""
    env = os.getenv("ENVIRONMENT")
    logger.info("크롬 드라이버 설정을 시작합니다...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    try:
        if env == "local":
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        elif env == "ec2":
            service = Service('/usr/bin/chromedriver')
        else:
            raise ValueError(f"지원하지 않는 환경입니다. local 또는 ec2만 가능: {env}")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        logger.error(f"크롬 드라이버 생성 중 오류 발생: {e}")
        raise

def click_element_by_xpath(driver, xpath, element_name, wait_time=10):
    """XPath로 요소를 찾아 클릭"""
    try:
        element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        element = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        element.click()
        logger.info(f"{element_name} 클릭 완료")
        time.sleep(2)
    except TimeoutException:
        logger.error(f"{element_name} 요소 시간 초과")
    except ElementClickInterceptedException:
        logger.error(f"{element_name} 클릭 불가 - 다른 요소에 가려짐")
    except NoSuchElementException:
        logger.error(f"{element_name} 요소를 찾을 수 없음")
    except Exception as e:
        logger.error(f"{element_name} 클릭 중 오류: {e}")

def perform_chart_actions(driver):
    """차트 설정 변경 및 지표 추가"""
    # 시간 단위 설정
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[1]",
        "시간 메뉴"
    )
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[1]/cq-menu-dropdown/cq-item[8]",
        "1시간 옵션"
    )
    
    # 기술적 지표 추가
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[3]",
        "지표 메뉴"
    )
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[3]/cq-menu-dropdown/cq-scroll/cq-studies/cq-studies-content/cq-item[15]",
        "볼린저 밴드"
    )

def capture_and_encode_screenshot(driver):
    """차트 스크린샷 캡처 및 인코딩"""
    try:
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png))
        img.thumbnail((2000, 2000))
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"스크린샷 캡처/인코딩 오류: {e}")
        return None

def generate_reflection(trades_df, current_market_data):
    """AI를 사용한 투자 분석 및 반성"""
    performance = calculate_performance(trades_df)
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API 키가 없습니다.")
        return None
    
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """당신은 비트코인 투자 분석 전문가입니다. 최근 거래 내역과 시장 상황을 분석하여
                           향후 투자 전략 개선을 위한 인사이트를 제공해주세요."""
            },
            {
                "role": "user",
                "content": f"""
                최근 거래 데이터:
                {trades_df.to_json(orient='records')}
                
                현재 시장 데이터:
                {current_market_data}
                
                최근 7일간 수익률: {performance:.2f}%
                
                다음 사항들에 대해 분석해주세요:
                1. 최근 거래 결정에 대한 평가
                2. 잘한 점과 개선이 필요한 점
                3. 향후 거래 전략 개선 방안
                4. 시장 데이터에서 발견된 패턴이나 트렌드
                
                250단어 이내로 작성해주세요.
                """
            }
        ]
    )

    try:
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI 응답 처리 중 오류 발생: {e}")
        return None

################################################################################
# 메인 트레이딩 로직
################################################################################

def ai_trading():
    """메인 AI 트레이딩 로직
    1. 시장 데이터 수집
    2. 기술적 분석 수행
    3. AI 분석 및 거래 결정
    4. 주문 실행
    5. 결과 기록
    """
 
 ### 데이터 수집
    global upbit
    
    # 잔고 조회
    all_balances = upbit.get_balances()
    filtered_balances = [balance for balance in all_balances if balance['currency'] in ['BTC', 'KRW']]
    
    # 시장 데이터 수집
    try:
        orderbook = pyupbit.get_orderbook("KRW-BTC")
        
        # 일봉/시간봉 데이터 수집 및 지표 계산
        df_daily = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=30)
        df_daily = dropna(df_daily)
        df_daily = add_indicators(df_daily)
        
        df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=24)
        df_hourly = dropna(df_hourly)
        df_hourly = add_indicators(df_hourly)

        # 부가 데이터 수집
        fear_greed_index = get_fear_and_greed_index()
        news_headlines = get_bitcoin_news()

        # 투자 전략 로드
        with open("strategy.txt", "r", encoding="utf-8") as f:
            strategy_text = f.read()

        # 차트 캡처
        driver = None
        try:
            driver = create_driver()
            driver.get("https://upbit.com/full_chart?code=CRIX.UPBIT.KRW-BTC")
            logger.info("차트 페이지 로드 완료")
            time.sleep(30)  # 차트 로딩 대기
            
            logger.info("차트 설정 시작")
            perform_chart_actions(driver)
            logger.info("차트 설정 완료")
            
            chart_image = capture_and_encode_screenshot(driver)
            logger.info("차트 캡처 완료")
            
        except Exception as e:
            logger.error(f"차트 캡처 중 오류 발생: {e}")
            chart_image = None
        finally:
            if driver:
                driver.quit()

        ### AI 분석 및 거래 실행
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not client.api_key:
            raise ValueError("OpenAI API 키가 없습니다.")

        # 데이터베이스 연결 및 거래 이력 분석
        with sqlite3.connect('bitcoin_trades.db') as conn:
            recent_trades = get_recent_trades(conn)
            
            current_market_data = {
                "fear_greed_index": fear_greed_index,
                "news_headlines": news_headlines,
                "orderbook": orderbook,
                "daily_ohlcv": df_daily.to_dict(),
                "hourly_ohlcv": df_hourly.to_dict()
            }
            
            reflection = generate_reflection(recent_trades, current_market_data)
            
            # AI 모델에 분석 요청
            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": f"""비트코인 전문 트레이더로서 현재 상황을 분석하고 매수/매도/홀딩 결정을 내려주세요.
                        다음 요소들을 고려해 주세요:

                        - 기술적 지표와 시장 데이터
                        - 최근 뉴스의 영향
                        - 공포탐욕지수
                        - 전반적인 시장 심리
                        - 차트 패턴과 추세
                        - 최근 거래 성과와 반성

                        최근 거래 분석:
                        {reflection}

                        원연토의 투자 방법을 참고하여 현재 상황을 판단해주세요:

                        {strategy_text}

                        응답 형식:
                        1. 결정 (매수/매도/홀딩)
                        2. 매수/매도시 비율(1-100%), 홀딩시 0%
                        3. 결정 이유

                        매수/매도 결정시 확신의 정도를 비율에 반영해주세요."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""현재 투자 상태: {json.dumps(filtered_balances)}
                                호가 데이터: {json.dumps(orderbook)}
                                일봉 데이터: {df_daily.to_json()}
                                시간봉 데이터: {df_hourly.to_json()}
                                뉴스 헤드라인: {json.dumps(news_headlines)}
                                공포탐욕지수: {json.dumps(fear_greed_index)}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{chart_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "type": "object",
                        "properties": {
                            "decision": {"type": "string", "enum": ["buy", "sell", "hold"]},
                            "percentage": {"type": "integer"},
                            "reason": {"type": "string"}
                        },
                        "required": ["decision", "percentage", "reason"]
                    }
                },
                max_tokens=4095
            )

            # AI 응답 처리
            result = TradingDecision.model_validate_json(response.choices[0].message.content)
            
            decision_kr = "매수" if result.decision == "buy" else "매도" if result.decision == "sell" else "홀딩"
            logger.info(f"AI 결정: {decision_kr}")
            logger.info(f"결정 이유: {result.reason}")

            # 주문 실행
            order_executed = False

            if result.decision == "buy":
                my_krw = upbit.get_balance("KRW")
                if my_krw is None:
                    logger.error("KRW 잔고 조회 실패")
                    return
                    
                buy_amount = my_krw * (result.percentage / 100) * 0.9995  # 수수료 고려
                if buy_amount > 5000:
                    logger.info(f"매수 주문 실행: 보유 KRW의 {result.percentage}%")
                    try:
                        order = upbit.buy_market_order("KRW-BTC", buy_amount)
                        if order:
                            logger.info(f"매수 주문 성공: {order}")
                            order_executed = True
                        else:
                            logger.error("매수 주문 실패")
                    except Exception as e:
                        logger.error(f"매수 주문 중 오류 발생: {e}")
                else:
                    logger.warning("매수 실패: 최소 주문금액(5000 KRW) 미달")

            elif result.decision == "sell":
                my_btc = upbit.get_balance("KRW-BTC")
                if my_btc is None:
                    logger.error("BTC 잔고 조회 실패")
                    return
                    
                sell_amount = my_btc * (result.percentage / 100)
                current_price = pyupbit.get_current_price("KRW-BTC")
                if sell_amount * current_price > 5000:
                    logger.info(f"매도 주문 실행: 보유 BTC의 {result.percentage}%")
                    try:
                        order = upbit.sell_market_order("KRW-BTC", sell_amount)
                        if order:
                            order_executed = True
                        else:
                            logger.error("매도 주문 실패")
                    except Exception as e:
                        logger.error(f"매도 주문 중 오류 발생: {e}")
                else:
                    logger.warning("매도 실패: 최소 주문금액(5000 KRW) 미달")

            # 거래 결과 기록
            time.sleep(2)  # API 호출 제한 고려
            balances = upbit.get_balances()
            btc_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'BTC'), 0)
            krw_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'KRW'), 0)
            btc_avg_buy_price = next((float(balance['avg_buy_price']) for balance in balances if balance['currency'] == 'BTC'), 0)
            current_btc_price = pyupbit.get_current_price("KRW-BTC")

            log_trade(conn, result.decision, result.percentage if order_executed else 0, result.reason, 
                     btc_balance, krw_balance, btc_avg_buy_price, current_btc_price, reflection)

    except Exception as e:
        logger.error(f"트레이딩 프로세스 중 오류 발생: {e}")
        return

if __name__ == "__main__":
    # 데이터베이스 초기화
    init_db()
    trading_in_progress = False

    def job():
        """정해진 시간에 실행될 트레이딩 작업"""
        global trading_in_progress
        if trading_in_progress:
            logger.warning("이미 거래가 진행 중입니다.")
            return
        try:
            trading_in_progress = True
            ai_trading()
        except Exception as e:
            logger.error(f"오류 발생: {e}")
        finally:
            trading_in_progress = False

    # 매일 정해진 시간에 실행
    schedule.every().day.at("09:00").do(job)
    schedule.every().day.at("15:00").do(job)
    schedule.every().day.at("21:00").do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)