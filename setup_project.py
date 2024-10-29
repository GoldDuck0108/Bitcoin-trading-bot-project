import os
import shutil

def create_project_structure():
    # 기본 경로 설정
    base_path = "/Users/ms/Desktop/ai/gptbitcoin"
    
    # 생성할 디렉토리 구조
    directories = [
        "config",
        "database",
        "trading",
        "utils",
        "data",
    ]
    
    # 메인 프로젝트 디렉토리 생성
    os.makedirs(base_path, exist_ok=True)
    
    # 하위 디렉토리 생성
    for dir_name in directories:
        dir_path = os.path.join(base_path, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        # __init__.py 파일 생성
        if dir_name != "data":
            with open(os.path.join(dir_path, "__init__.py"), "w") as f:
                pass

    # 파일들의 내용 정의
    files_content = {
        os.path.join("config", "settings.py"): '''
import os
from dotenv import load_dotenv

load_dotenv()

UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
''',
        
        os.path.join("database", "models.py"): '''
from pydantic import BaseModel

class TradingDecision(BaseModel):
    decision: str
    percentage: int
    reason: str
''',
        
        os.path.join("database", "operations.py"): '''
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os

def init_db():
    conn = sqlite3.connect('bitcoin_trades.db')
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  decision TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  btc_balance REAL,
                  krw_balance REAL,
                  btc_avg_buy_price REAL,
                  btc_krw_price REAL,
                  reflection TEXT)""")
    conn.commit()
    return conn

def log_trade(conn, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection=''):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, decision, percentage, reason, btc_balance, krw_balance, btc_avg_buy_price, btc_krw_price, reflection))
    conn.commit()

def get_recent_trades(conn, days=7):
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
    c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (seven_days_ago,))
    columns = [column[0] for column in c.description]
    return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)
''',

        os.path.join("utils", "logger.py"): '''
import logging

def setup_logger():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    return logger

logger = setup_logger()
''',

        os.path.join("utils", "api_utils.py"): '''
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import logging
from gptbitcoin.config.settings import SERPAPI_API_KEY

logger = logging.getLogger(__name__)

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

def get_bitcoin_news():
    if not SERPAPI_API_KEY:
        logger.error("SERPAPI API key is missing.")
        return None
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_news",
        "q": "btc",
        "api_key": SERPAPI_API_KEY
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
        logger.error(f"Error fetching news: {e}")
        return []
''',

        os.path.join("trading", "indicators.py"): '''
import ta
from ta.utils import dropna

def add_indicators(df):
    df = dropna(df)
    # 볼린저 밴드
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()
    
    # RSI
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
''',

        "main.py": '''
import schedule
import time
from gptbitcoin.trading.execution import ai_trading
from gptbitcoin.database.operations import init_db
from gptbitcoin.utils.logger import logger

trading_in_progress = False

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

if __name__ == "__main__":
    init_db()
    
    # 스케줄링된 실행
    schedule.every().day.at("09:00").do(job)
    schedule.every().day.at("15:00").do(job)
    schedule.every().day.at("21:00").do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
''',

        "requirements.txt": '''
python-dotenv==1.0.0
pyupbit==0.2.33
pandas==2.1.2
openai==1.3.0
ta==0.10.2
requests==2.31.0
Pillow==10.1.0
selenium==4.15.2
youtube-transcript-api==0.6.1
pydantic==2.4.2
schedule==1.2.1
webdriver-manager==4.0.1
''',

        ".env": '''
UPBIT_ACCESS_KEY=your_access_key_here
UPBIT_SECRET_KEY=your_secret_key_here
OPENAI_API_KEY=your_openai_api_key_here
SERPAPI_API_KEY=your_serpapi_api_key_here
ENVIRONMENT=local
'''
    }

    # 파일 생성
    for file_path, content in files_content.items():
        full_path = os.path.join(base_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content.strip())

    # 전략 파일 생성
    with open(os.path.join(base_path, "data", "strategy.txt"), "w", encoding="utf-8") as f:
        f.write("# 투자 전략이 여기에 들어갑니다.")

    print("프로젝트 구조가 성공적으로 생성되었습니다!")

if __name__ == "__main__":
    create_project_structure()