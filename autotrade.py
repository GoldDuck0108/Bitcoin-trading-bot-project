# 필수 라이브러리 임포트
import os  # 운영체제 관련 기능 (환경변수, 파일경로 등)
from dotenv import load_dotenv  # .env 파일에서 환경변수 로드
import pyupbit  # 업비트 API 사용을 위한 라이브러리
import pandas as pd  # 데이터 분석/처리용 라이브러리
import json  # JSON 데이터 처리
from openai import OpenAI  # OpenAI API 사용 (GPT 모델)
import ta  # 기술적 분석 지표 계산 라이브러리
from ta.utils import dropna  # 결측값 처리

# 시간 관련
import time  # 시간 지연, 대기 기능
from datetime import datetime, timedelta  # 날짜/시간 처리

# 웹 관련
import requests  # HTTP 요청 처리
import base64  # 이미지 인코딩
from PIL import Image  # 이미지 처리
import io  # 입출력 스트림 처리

# Selenium 관련 (웹 자동화)
from selenium import webdriver  # 웹 브라우저 자동화
from selenium.webdriver.chrome.service import Service  # 크롬드라이버 서비스
from selenium.webdriver.chrome.options import Options  # 크롬 옵션 설정
from selenium.webdriver.common.by import By  # 요소 찾기 방식 지정
from selenium.webdriver.support.ui import WebDriverWait  # 요소 대기
from selenium.webdriver.support import expected_conditions as EC  # 조건부 대기
# Selenium 예외처리
from selenium.common.exceptions import (
   TimeoutException,  # 시간 초과
   ElementClickInterceptedException,  # 클릭 불가
   WebDriverException,  # 드라이버 오류
   NoSuchElementException  # 요소 없음
)

# 기타 유틸리티
import logging  # 로깅 처리
from youtube_transcript_api import YouTubeTranscriptApi  # 유튜브 자막 추출
from pydantic import BaseModel  # 데이터 모델 정의
import sqlite3  # SQLite 데이터베이스 처리
import schedule  # 작업 스케줄링

################################################################################
# 기본 설정 및 초기화 부분
################################################################################

# .env 파일에서 환경변수(API 키 등) 불러오기
load_dotenv()

# 로깅 설정 - 프로그램 실행 상태와 정보를 콘솔에 출력하기 위한 설정
# INFO 레벨로 설정하여 중요 정보만 출력
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 업비트 API 연결 설정
# .env 파일에서 API 키 불러오기
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
if not access or not secret:
   logger.error("API 키를 찾을 수 없습니다. .env 파일을 확인해주세요.")
   raise ValueError("API 키가 없습니다. .env 파일을 확인해주세요.")
upbit = pyupbit.Upbit(access, secret)

################################################################################
# 데이터 모델 및 데이터베이스 관련 클래스/함수
################################################################################

# AI의 거래 결정을 저장하기 위한 데이터 모델 클래스
class TradingDecision(BaseModel):
   decision: str  # 결정: 매수/매도/홀딩
   percentage: int  # 거래 비율 (%)
   reason: str  # 결정 이유

def init_db():
   """
   SQLite 데이터베이스 초기화 및 테이블 생성
   Returns:
       sqlite3.Connection: 데이터베이스 연결 객체
   """
   conn = sqlite3.connect('bitcoin_trades.db')
   c = conn.cursor()
   # 거래 내역을 저장할 테이블 생성
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
   """
   거래 내역을 데이터베이스에 기록
   Args:
       conn: 데이터베이스 연결 객체
       decision: 거래 결정 (매수/매도/홀딩)
       percentage: 거래 비율
       reason: 거래 이유
       btc_balance: BTC 잔고
       krw_balance: KRW 잔고
       btc_avg_buy_price: BTC 평균 매수가
       btc_krw_price: 현재 BTC 가격
       reflection: AI의 분석 및 반성
   """
   c = conn.cursor()
   timestamp = datetime.now().isoformat()
   c.execute("""INSERT INTO trades 
                VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
             (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection))
   conn.commit()

def get_recent_trades(conn, days=7):
   """
   최근 거래 내역 조회
   Args:
       conn: 데이터베이스 연결 객체
       days: 조회할 기간(일)
   Returns:
       DataFrame: 최근 거래 내역
   """
   c = conn.cursor()
   seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
   c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (seven_days_ago,))
   columns = [column[0] for column in c.description]
   return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)

def calculate_performance(trades_df):
   """
   투자 성과 계산 (수익률)
   Args:
       trades_df: 거래 내역 데이터프레임
   Returns:
       float: 수익률(%)
   """
   if trades_df.empty:
       return 0  # 거래 기록이 없는 경우 0% 반환
   # 초기 자산 계산 (KRW + BTC * 현재 가격)
   initial_balance = trades_df.iloc[-1]['krw_balance'] + trades_df.iloc[-1]['btc_balance'] * trades_df.iloc[-1]['btc_krw_price']
   # 최종 자산 계산
   final_balance = trades_df.iloc[0]['krw_balance'] + trades_df.iloc[0]['btc_balance'] * trades_df.iloc[0]['btc_krw_price']
   return (final_balance - initial_balance) / initial_balance * 100

def generate_reflection(trades_df, current_market_data):
    """
    AI를 사용하여 최근 투자 내역과 시장 데이터 분석
    Args:
        trades_df: 거래 내역 데이터프레임
        current_market_data: 현재 시장 데이터
    Returns:
        str: AI의 분석 결과
    """
    performance = calculate_performance(trades_df)
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API 키가 없거나 유효하지 않습니다.")
        return None
    
    # OpenAI API 호출로 AI의 반성 일기 및 개선 사항 생성 요청
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "AI 트레이딩 어시스턴트로서 최근 거래 성과와 시장 상황을 분석하여 향후 거래 개선을 위한 인사이트를 제공합니다."
            },
            {
                "role": "user",
                "content": f"""
                최근 거래 데이터:
                {trades_df.to_json(orient='records')}
                
                현재 시장 데이터:
                {current_market_data}
                
                최근 7일간 수익률: {performance:.2f}%
                
                다음 사항들을 분석해주세요:
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
        response_content = response.choices[0].message.content
        return response_content
    except (IndexError, AttributeError) as e:
        logger.error(f"AI 응답 추출 중 오류 발생: {e}")
        return None

    try:
        response_content = response.choices[0].message.content
        return response_content
    except (IndexError, AttributeError) as e:
        logger.error(f"Error extracting response content: {e}")
        return None

# 데이터프레임에 보조 지표를 추가하는 함수
def add_indicators(df):
    # 볼린저 밴드 추가
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()
    
    # RSI (Relative Strength Index) 추가
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    
    # MACD (Moving Average Convergence Divergence) 추가
    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    # 이동평균선 (단기, 장기)
    df['sma_20'] = ta.trend.SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['ema_12'] = ta.trend.EMAIndicator(close=df['close'], window=12).ema_indicator()
    
    return df

# 공포 탐욕 지수 조회
def get_fear_and_greed_index():
    url = "https://api.alternative.me/fng/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['data'][0]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Fear and Greed Index: {e}")
        return None

# 뉴스 데이터 가져오기
def get_bitcoin_news():
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        logger.error("SERPAPI API key is missing.")
        return None  # 또는 함수 종료
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
        headlines = []
        for item in news_results:
            headlines.append({
                "title": item.get("title", ""),
                "date": item.get("date", "")
            })
        
        return headlines[:5]
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        return []
        
# 유튜브 자막 데이터 가져오기
def get_combined_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        combined_text = ' '.join(entry['text'] for entry in transcript)
        return combined_text
    except Exception as e:
        logger.error(f"Error fetching YouTube transcript: {e}")
        return ""

#### Selenium 관련 함수
def create_driver():
    env = os.getenv("ENVIRONMENT")
    logger.info("ChromeDriver 설정 중...")
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
            raise ValueError(f"Unsupported environment. Only local or ec2: {env}")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"ChromeDriver 생성 중 오류 발생: {e}")
        raise

# XPath로 Element 찾기
def click_element_by_xpath(driver, xpath, element_name, wait_time=10):
    try:
        element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # 요소가 뷰포트에 보일 때까지 스크롤
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        # 요소가 클릭 가능할 때까지 대기
        element = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        element.click()
        logger.info(f"{element_name} 클릭 완료")
        time.sleep(2)  # 클릭 후 잠시 대기
    except TimeoutException:
        logger.error(f"{element_name} 요소를 찾는 데 시간이 초과되었습니다.")
    except ElementClickInterceptedException:
        logger.error(f"{element_name} 요소를 클릭할 수 없습니다. 다른 요소에 가려져 있을 수 있습니다.")
    except NoSuchElementException:
        logger.error(f"{element_name} 요소를 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"{element_name} 클릭 중 오류 발생: {e}")
# 차트 클릭하기
def perform_chart_actions(driver):
    # 시간 메뉴 클릭
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[1]",
        "시간 메뉴"
    )
    # 1시간 옵션 선택
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[1]/cq-menu-dropdown/cq-item[8]",
        "1시간 옵션"
    )
    # 지표 메뉴 클릭
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[3]",
        "지표 메뉴"
    )
    # 볼린저 밴드 옵션 선택
    click_element_by_xpath(
        driver,
        "/html/body/div[1]/div[2]/div[3]/span/div/div/div[1]/div/div/cq-menu[3]/cq-menu-dropdown/cq-scroll/cq-studies/cq-studies-content/cq-item[15]",
        "볼린저 밴드 옵션"
    )
# 스크린샷 캡쳐 및 base64 이미지 인코딩
def capture_and_encode_screenshot(driver):
    try:
        # 스크린샷 캡처
        png = driver.get_screenshot_as_png()
        # PIL Image로 변환
        img = Image.open(io.BytesIO(png))
        # 이미지가 클 경우 리사이즈 (OpenAI API 제한에 맞춤)
        img.thumbnail((2000, 2000))
        # 이미지를 바이트로 변환
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        # base64로 인코딩
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return base64_image
    except Exception as e:
        logger.error(f"스크린샷 캡처 및 인코딩 중 오류 발생: {e}")
        return None

### 메인 AI 트레이딩 로직
def ai_trading():
    """메인 AI 트레이딩 로직
    1. 시장 데이터 수집
    2. 기술적 분석 수행
    3. AI 모델에 분석 요청
    4. 거래 실행
    5. 결과 기록
    """
    global upbit
    
    # 1. 현재 잔고 확인
    all_balances = upbit.get_balances()
    filtered_balances = [balance for balance in all_balances if balance['currency'] in ['BTC', 'KRW']]
        
    # 2. 오더북(호가 데이터) 조회
    orderbook = pyupbit.get_orderbook("KRW-BTC")
    
    # 3. 차트 데이터 조회 및 보조지표 추가
    df_daily = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=30)
    df_daily = dropna(df_daily)
    df_daily = add_indicators(df_daily)
    
    df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    df_hourly = dropna(df_hourly)
    df_hourly = add_indicators(df_hourly)

    # 4. 공포 탐욕 지수 가져오기
    fear_greed_index = get_fear_and_greed_index()

    # 5. 뉴스 헤드라인 가져오기
    news_headlines = get_bitcoin_news()

    # 6. YouTube 자막 데이터 가져오기
    # youtube_transcript = get_combined_transcript("3XbtEX3jUv4")
    f = open("strategy.txt", "r", encoding="utf-8")
    youtube_transcript = f.read()
    f.close()

    # 7. Selenium으로 차트 캡처
    driver = None
    try:
        driver = create_driver()
        driver.get("https://upbit.com/full_chart?code=CRIX.UPBIT.KRW-BTC")
        logger.info("페이지 로드 완료")
        time.sleep(30)  # 페이지 로딩 대기 시간 증가
        logger.info("차트 작업 시작")
        perform_chart_actions(driver)
        logger.info("차트 작업 완료")
        chart_image = capture_and_encode_screenshot(driver)
        logger.info(f"스크린샷 캡처 완료.")
    except WebDriverException as e:
        logger.error(f"캡쳐시 WebDriver 오류 발생: {e}")
        chart_image = None
    except Exception as e:
        logger.error(f"차트 캡처 중 오류 발생: {e}")
        chart_image = None
    finally:
        if driver:
            driver.quit()

    ### AI에게 데이터 제공하고 판단 받기
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    try:
        # 데이터베이스 연결
        with sqlite3.connect('bitcoin_trades.db') as conn:
            # 최근 거래 내역 가져오기
            recent_trades = get_recent_trades(conn)
            
            # 현재 시장 데이터 수집 (기존 코드에서 가져온 데이터 사용)
            current_market_data = {
                "fear_greed_index": fear_greed_index,
                "news_headlines": news_headlines,
                "orderbook": orderbook,
                "daily_ohlcv": df_daily.to_dict(),
                "hourly_ohlcv": df_hourly.to_dict()
            }
            
            # 반성 및 개선 내용 생성
            reflection = generate_reflection(recent_trades, current_market_data)
            
            # AI 모델에 반성 내용 제공
            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are an expert in Bitcoin investing. Analyze the provided data and determine whether to buy, sell, or hold at the current moment. Consider the following in your analysis:

                        - Technical indicators and market data
                        - Recent news headlines and their potential impact on Bitcoin price
                        - The Fear and Greed Index and its implications
                        - Overall market sentiment
                        - Patterns and trends visible in the chart image
                        - Recent trading performance and reflection

                        Recent trading reflection:
                        {reflection}

                        Particularly important is to always refer to the trading method of 'Wonyyotti', a legendary Korean investor, to assess the current situation and make trading decisions. Wonyyotti's trading method is as follows:

                        {youtube_transcript}

                        Based on this trading method, analyze the current market situation and make a judgment by synthesizing it with the provided data and recent performance reflection.

                        Response format:
                        1. Decision (buy, sell, or hold)
                        2. If the decision is 'buy', provide a percentage (1-100) of available KRW to use for buying.
                        If the decision is 'sell', provide a percentage (1-100) of held BTC to sell.
                        If the decision is 'hold', set the percentage to 0.
                        3. Reason for your decision

                        Ensure that the percentage is an integer between 1 and 100 for buy/sell decisions, and exactly 0 for hold decisions.
                        Your percentage should reflect the strength of your conviction in the decision based on the analyzed data."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Current investment status: {json.dumps(filtered_balances)}
                Orderbook: {json.dumps(orderbook)}
                Daily OHLCV with indicators (30 days): {df_daily.to_json()}
                Hourly OHLCV with indicators (24 hours): {df_hourly.to_json()}
                Recent news headlines: {json.dumps(news_headlines)}
                Fear and Greed Index: {json.dumps(fear_greed_index)}"""
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
                        "name": "trading_decision",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "decision": {"type": "string", "enum": ["buy", "sell", "hold"]},
                                "percentage": {"type": "integer"},
                                "reason": {"type": "string"}
                            },
                            "required": ["decision", "percentage", "reason"],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=4095
            )

            # Pydantic을 사용하여 AI의 트레이딩 결정 구조를 정의
            try:
                result = TradingDecision.model_validate_json(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"Error parsing AI response: {e}")
                return
            
            logger.info(f"AI Decision: {result.decision.upper()}")
            logger.info(f"Decision Reason: {result.reason}")

            order_executed = False

            if result.decision == "buy":
                my_krw = upbit.get_balance("KRW")
                if my_krw is None:
                    logger.error("Failed to retrieve KRW balance.")
                    return
                buy_amount = my_krw * (result.percentage / 100) * 0.9995  # 수수료 고려
                if buy_amount > 5000:
                    logger.info(f"Buy Order Executed: {result.percentage}% of available KRW")
                    try:
                        order = upbit.buy_market_order("KRW-BTC", buy_amount)
                        if order:
                            logger.info(f"Buy order executed successfully: {order}")
                            order_executed = True
                        else:
                            logger.error("Buy order failed.")
                    except Exception as e:
                        logger.error(f"Error executing buy order: {e}")
                else:
                    logger.warning("Buy Order Failed: Insufficient KRW (less than 5000 KRW)")
            elif result.decision == "sell":
                my_btc = upbit.get_balance("KRW-BTC")
                if my_btc is None:
                    logger.error("Failed to retrieve KRW balance.")
                    return
                sell_amount = my_btc * (result.percentage / 100)
                current_price = pyupbit.get_current_price("KRW-BTC")
                if sell_amount * current_price > 5000:
                    logger.info(f"Sell Order Executed: {result.percentage}% of held BTC")
                    try:
                        order = upbit.sell_market_order("KRW-BTC", sell_amount)
                        if order:
                            order_executed = True
                        else:
                            logger.error("Buy order failed.")
                    except Exception as e:
                        logger.error(f"Error executing sell order: {e}")
                else:
                    logger.warning("Sell Order Failed: Insufficient BTC (less than 5000 KRW worth)")
            
            # 거래 실행 여부와 관계없이 현재 잔고 조회
            time.sleep(2)  # API 호출 제한을 고려하여 잠시 대기
            balances = upbit.get_balances()
            btc_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'BTC'), 0)
            krw_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'KRW'), 0)
            btc_avg_buy_price = next((float(balance['avg_buy_price']) for balance in balances if balance['currency'] == 'BTC'), 0)
            current_btc_price = pyupbit.get_current_price("KRW-BTC")

            # 거래 기록을 DB에 저장하기
            log_trade(conn, result.decision, result.percentage if order_executed else 0, result.reason, 
                    btc_balance, krw_balance, btc_avg_buy_price, current_btc_price, reflection)
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return

if __name__ == "__main__":
    # 데이터베이스 초기화
    init_db()

    # 중복 실행 방지를 위한 변수
    trading_in_progress = False

    # 트레이딩 작업을 수행하는 함수
    def job():
        global trading_in_progress
        if trading_in_progress:
            logger.warning("Trading job is already in progress, skipping this run.")
            return
        try:
            trading_in_progress = True
            ai_trading()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        finally:
            trading_in_progress = False

    ## 테스트용 바로 실행
    # job()

    ## 매일 특정 시간(예: 오전 9시, 오후 3시, 오후 9시)에 실행
    schedule.every().day.at("09:00").do(job)
    schedule.every().day.at("15:00").do(job)
    schedule.every().day.at("21:00").do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)