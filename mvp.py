import os
from dotenv import load_dotenv
load_dotenv()
import json

def ai_trading():
    import pandas as pd
    import pyupbit

    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    upbit = pyupbit.Upbit(access, secret) 
    
    # DataFrame 출력 설정 
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('expand_frame_repr', False)
    pd.set_option('display.max_rows', None)

    df = pyupbit.get_ohlcv("KRW-BTC", count=30, interval="day")

    from openai import OpenAI
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "You are an expert in Bitcoin investing. Tell me whether to buy, sell, or hold at this time based on the chart data provided. Response must be in valid JSON format with decision and reason keys."
            },
            {
                "role": "user",
                "content": df.to_json()
            }
        ]
    )

    result = json.loads(response.choices[0].message.content)
    
    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Reason: {result['reason']}###")

    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        if my_krw*0.9995>5000:
            print("### Buy Order Executed ###")
            print(upbit.buy_market_order("KRW-BTC", my_krw*0.9995))
        else:
            print("### Buy Order Failed : Insufficient KRW(less than 5000 KRW)###")
    elif result["decision"] == "sell":
        my_btc = upbit.get_balance("KRW-BTC")
        current_price = pyupbit.get_orderbook(ticker="KRW-BTC")['orderbook_units'][0]["ask_price"]
        if my_btc*current_price >5000:
            print("### Sell Order Executed ###")
            print(upbit.sell_market_order("KRW-BTC", upbit.get_balance("KRW-BTC")))
        else:
            print("실패 : btc 5000원 미만")
    elif result["decision"] == "hold":
        print("hold:",result["reason"])

while True:
    import time
    time.sleep(10)
    ai_trading()