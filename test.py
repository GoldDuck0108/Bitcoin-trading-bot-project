from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")  # 브라우저를 최대화하여 시작
    return chrome_options

def create_driver():
    logger.info("ChromeDriver 설정 중...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=setup_chrome_options())
    return driver

def capture_full_page_screenshot(driver, url, filename):
    logger.info(f"{url} 로딩 중...")
    driver.get(url)
    
    # 페이지 로딩을 위한 대기 시간
    logger.info("페이지 로딩 대기 중...")
    time.sleep(10)  # 페이지 로딩을 위해 10초 대기
    
    logger.info("전체 페이지 스크린샷 촬영 중...")
    driver.save_screenshot(filename)
    logger.info(f"스크린샷이 성공적으로 저장되었습니다: {filename}")

def main():
    driver = None
    try:
        driver = create_driver()
        capture_full_page_screenshot(
            driver, 
            "https://upbit.com/full_chart?code=CRIX.UPBIT.KRW-BTC",
            "upbit_btc_full_chart.png"
        )
    except Exception as e:
        logger.error(f"오류 발생: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()