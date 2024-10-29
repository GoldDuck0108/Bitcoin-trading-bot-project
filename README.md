echo "# Bitcoin Trading Bot

## 설치 방법
1. 가상환경 생성 및 활성화:
   python -m venv myenv
   source myenv/bin/activate  # Mac/Linux
   myenv\\Scripts\\activate  # Windows

2. 필요한 패키지 설치:
   pip install -r requirements.txt

3. .env 파일 생성 및 API 키 설정:
   UPBIT_ACCESS_KEY=your_access_key_here
   UPBIT_SECRET_KEY=your_secret_key_here
   OPENAI_API_KEY=your_openai_api_key_here
   SERPAPI_API_KEY=your_serpapi_api_key_here
   ENVIRONMENT=local

4. 실행 방법:
   - 트레이딩 봇 실행: python main.py
   - 대시보드 실행: streamlit run streamlit_app.py

## 주의사항
- API 키는 반드시 본인의 키로 설정해야 합니다.
- 실제 거래가 이루어지므로 주의가 필요합니다.
- 처음에는 소액으로 테스트하는 것을 추천합니다.

## 파일 설명
- main.py: 메인 트레이딩 봇 코드
- streamlit_app.py: 거래 현황 대시보드
- strategy.txt: 투자 전략 파일
- requirements.txt: 필요한 패키지 목록" > /Users/ms/Desktop/ai/bitcoin/README.md