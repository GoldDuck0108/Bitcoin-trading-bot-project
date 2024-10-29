# # requirements.txt
# python-dotenv
# pyupbit
# pandas
# openai
# ta
# requests
# Pillow
# selenium
# youtube-transcript-api
# pydantic
# schedule
# webdriver_manager

# setup.py
import subprocess
import sys

def install_requirements():
    """비트코인 트레이딩 봇에 필요한 패키지들을 설치합니다."""
    try:
        # pip를 사용하여 requirements.txt의 패키지들을 설치
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("모든 필수 패키지가 성공적으로 설치되었습니다!")
    except subprocess.CalledProcessError as e:
        print(f"패키지 설치 중 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_requirements()