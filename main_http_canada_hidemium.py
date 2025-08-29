import sys
import time
import random
import requests
import string
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from log import logger
from webdriver_manager.chrome import ChromeDriverManager
import json
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import traceback
import threading
from queue import Queue, Empty
import pyotp
import os

service = Service(ChromeDriverManager(driver_version="137.0.7151.122").install())
stop_event = threading.Event()
pause_event = threading.Event()
failed_start_profile_count = 0
failed_account_creation_count = 0
max_failed_account_creation = 0
account_creation_lock = threading.Lock()
def increment_failed_account_creation():
    global failed_account_creation_count, max_failed_account_creation
    threading.current_thread().name = "Monitor"
    with account_creation_lock:
        failed_account_creation_count += 1
        logger.warning(f"⚠️ Số lỗi tạo tài khoản hiện tại: {failed_account_creation_count}/{max_failed_account_creation}")
        
        if failed_account_creation_count >= max_failed_account_creation:
            logger.warning(f"🛑 Đã đạt tới số lỗi tối đa ({max_failed_account_creation}). Tạm dừng tất cả luồng trong 1 giờ...")
            pause_event.set()
            
            # Tạo thread riêng để chờ 1 giờ và reset
            def wait_and_resume():
                time.sleep(3600)  # Chờ 1 giờ (3600 giây)
                global failed_account_creation_count
                with account_creation_lock:
                    failed_account_creation_count = 0
                    logger.info("✅ Đã chờ đủ 1 giờ. Tiếp tục tạo tài khoản...")
                    pause_event.clear()
            
            threading.Thread(target=wait_and_resume, daemon=True).start()

# Hàm đọc config.json
def read_config(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"CẢNH BÁO: Không tìm thấy tệp {file_path}. Chạy mà không dùng dữ liệu từ tệp.")
        return {}
    
def read_link_sp():
    try:
        with open("link san pham.txt", 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("CẢNH BÁO: Không tìm thấy tệp link san pham.txt. Chạy mà không dùng dữ liệu từ tệp.")
        return []

def read_link_sp_canada():
    try:
        with open("link san pham canada.txt", 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("CẢNH BÁO: Không tìm thấy tệp link san pham canada.txt. Chạy mà không dùng dữ liệu từ tệp.")
        return []

config = read_config("config.json")

# Hidemium API client
class HidemiumAPI:
    def __init__(self):
        self.base_url = getattr(config, "hidemium_server", "http://127.0.0.1:2222")
        self.session = requests.Session()

    def create_profile(self, proxy, profile_name="AmazonProfile"):
        # Tạo cấu hình mới với proxy HTTP và hệ điều hành Android
        # Format proxy as "HTTP|host|port|user|password"
        proxy_str = ""
        if proxy:
            # Accept proxy in "host:port:user:pass" or "host:port" format
            parts = proxy.split(":")
            if len(parts) == 4:
                host, port, user, password = parts
                proxy_str = f"HTTP|{host}|{port}|{user}|{password}"
            elif len(parts) == 2:
                host, port = parts
                proxy_str = f"HTTP|{host}|{port}||"
            else:
                proxy_str = proxy  # fallback, use as is

        payload = {
            "os": "mac",
            "osVersion": "14.3.0",
            "browser": "chrome",
            "version": "137",
            "userAgent": "",
            "canvas": True,
            "webGLImage": True,
            "audioContext": False,
            "webGLMetadata": True,
            "webGLVendor": "",
            "webGLMetadataRenderer": "",
            "clientRectsEnable": True,
            "noiseFont": False,
            "language": "vi-VN",
            "deviceMemory": 4,
            "hardwareConcurrency": 32,
            "resolution": "1280x800",
            "StartURL": getattr(config, "reg_link", "https://www.amazon.com/amazonprime"),
            "command": "--lang=vi",
            "name": f"{profile_name}_{random.randint(1000, 9999)}",
            "folder_name": "All",
            "proxy": proxy_str
        }
        response = self.session.post(f"{self.base_url}/create-profile-custom?is_local=true", json=payload)
        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            # logger.info(f" Đã tạo cấu hình với proxy {proxy}: {result}")
            return result.get("uuid")
        logger.error(f"CẢNH BÁO: Không tạo được cấu hình với proxy {proxy}")
        return None

    def start_profile(self, profile_id):
        global failed_start_profile_count
        # Khởi động trình duyệt cho cấu hình
        response = self.session.get(f"{self.base_url}/openProfile?uuid={profile_id}")
        if response.status_code == 200:
            result = response.json()
            # logger.info(f" Đã khởi động cấu hình {profile_id} với debug port: {result}")
            debug_port = result.get("data", {}).get("remote_port") or result.get("remote_port")
            if debug_port:
                return {"remote_debugging_address": f"127.0.0.1:{debug_port}"}
        logger.error(f"CẢNH BÁO: Không khởi động được cấu hình {profile_id}")
        failed_start_profile_count += 1
        if (failed_start_profile_count >= 10):
            stop_event.set()
            time.sleep(5)
            os._exit(1)
        return None

    def close_profile(self, profile_id):
        # Đóng trình duyệt
        self.session.post(f"{self.base_url}/closeProfile?uuid={profile_id}")

    def delete_profile(self, profile_id):
        # Xóa cấu hình
        # response = self.session.delete(f"{self.base_url}/api/browsers/{profile_id}")
        # if response.status_code == 200:
        #     return True
        # logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id}")
        # return False
        return True

# ShopGmail9999 API client
class ShopGmailAPI:
    def __init__(self, apikey):
        self.base_url = "https://api.shopgmail9999.com/api/ApiV2"
        self.apikey = apikey
        self.session = requests.Session()

    def create_gmail_account(self):
        # Tạo Gmail mới bằng API CreateOrder
        api_url = f"{self.base_url}/CreateOrder"
        params = {
            "apikey": self.apikey,
            "service": "amazon"
        }
        try:
            response = self.session.get(api_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    email = data.get("data", {}).get("email")
                    orderid = data.get("data", {}).get("orderid")
                    if email and orderid:
                        logger.info(f" Tạo Gmail thành công: {email}")
                        return email, orderid
                    else:
                        logger.warning("CẢNH BÁO: Không tìm thấy email hoặc orderid trong phản hồi API")
                        return None, None
                else:
                    logger.warning(f"CẢNH BÁO: Lỗi khi tạo Gmail: {data.get('msg')}")
                    return None, None
            else:
                # logger.warning(f"CẢNH BÁO: Lỗi khi gọi API CreateOrder: {response.status_code} - {response.text}.Tiến hành tạo lại..." )
                return None, None
        except Exception as e:
            # logger.warning(f"CẢNH BÁO: Lỗi khi gọi API CreateOrder: {str(e)}. Tiến hành tạo lại...")
            return None, None

    def get_otp(self, orderid):
        # Lấy OTP từ CheckOtp2
        api_url = f"{self.base_url}/CheckOtp2"
        params = {
            "apikey": self.apikey,
            "orderid": orderid,
            "getbody": False
        }
        try:
            for _ in range(15):  # Thử tối đa 30 lần, cách nhau 5 giây
                response = self.session.get(api_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success" and data.get("data", {}).get("status") == "success":
                        otp = data.get("data", {}).get("otp")
                        if otp:
                            logger.info(f" Lấy OTP thành công: {otp}")
                            return otp
                        elif data.get("data", {}).get("status") in ["error-token", "timeout"]:
                            logger.warning(f"CẢNH BÁO: Lỗi OTP: {data.get('data', {}).get('status')}")
                            return None
                time.sleep(5)  # Chờ 5 giây trước khi thử lại
            logger.warning("CẢNH BÁO: Hết thời gian chờ OTP")
            return None
        except Exception as e:
            logger.error(f"CẢNH BÁO: Lỗi khi gọi API CheckOtp2: {str(e)}")
            return None

# Hàm kiểm tra CAPTCHA
def handle_captcha(driver, email):
    captcha_selectors = [
        (By.ID, "captcha-container"),
        (By.ID, "captchacharacters"),
        (By.ID, "cvf-aamation-challenge-iframe"),
        (By.ID, "aacb-captcha-header")
    ]
    try:
        WebDriverWait(driver, 5).until(
            lambda d: any(d.find_elements(*sel) for sel in captcha_selectors)
        )
        logger.warning(f"CẢNH BÁO: Phát hiện CAPTCHA hoặc SDT cho {email}.")
        return False
    except:
        return True

# Hàm mô phỏng gõ giống con người
def human_type(element, text):
    time.sleep(3)
    for i, char in enumerate(text):  # ✅ SỬA chỗ này
        element.send_keys(char)
        if i % random.randint(3, 7) == 0:
            time.sleep(random.uniform(0.5, 1.0))  # Nghỉ lâu hơn
        else:
            time.sleep(random.uniform(0.2, 0.4))  # Gõ chậm hơn bình thường
    time.sleep(3)

# Hàm đọc dòng từ tệp
def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning(f"CẢNH BÁO: Không tìm thấy tệp {file_path}. Chạy mà không dùng dữ liệu từ tệp.")
        return []

lock = threading.Lock()

def remove_line(file_path, index):
    with lock:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if index < len(lines):
            del lines[index]
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

# Hàm lưu chi tiết tài khoản
def save_account(email, password, tfa_code, file_path="output.txt"):
    if not is_account_existed(email, file_path):
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"{email}|{password}|{tfa_code}\n")
        logger.info(f" Đã lưu tài khoản {email} vào {file_path}")
    else:
        logger.warning(f"CẢNH BÁO: Tài khoản {email} đã tồn tại, không lưu lại")

def is_account_existed(email, file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith(email):
                    return True
    except FileNotFoundError:
        pass
    return False

# Hàm ghi log tài khoản lỗi
def log_failed_account(email, file_path):
    if not is_account_existed(email, file_path):
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"{email}\n")
        if "captcha.txt" not in file_path:
            logger.warning(f"CẢNH BÁO: Đã ghi tài khoản lỗi {email} vào {file_path}")
    elif "captcha.txt" not in file_path:
        logger.info(f" Tài khoản {email} đã có trong {file_path}, không ghi lại")


def click_element_deprecated(driver, element, timeout=10):
    """Deprecated: Use driver.execute_script("arguments[0].click();", element) instead"""
    try:
        time.sleep(3)
        element.click()
        
    except Exception as ex:
        try:
            # Scroll element vào giữa màn hình
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            # Click bằng JS
            driver.execute_script("arguments[0].click();", element)
        except Exception as e:
            raise ex

# Common click functions
def click_by_id(driver, element_id, scroll_first=True):
    """Click element by ID using document.querySelector"""
    try:
        if scroll_first:
            driver.execute_script(f"document.querySelector('#{element_id}').scrollIntoView({{block: 'center'}});")
            time.sleep(0.5)
        driver.execute_script(f"document.querySelector('#{element_id}').click();")
        return True
    except Exception as e:
        logger.warning(f"Failed to click element #{element_id}: {repr(e)}")
        return False

def click_by_selector(driver, selector, scroll_first=True):
    """Click element by CSS selector using document.querySelector"""
    try:
        if scroll_first:
            driver.execute_script(f"document.querySelector(arguments[0]).scrollIntoView({{block: 'center'}});", selector)
            time.sleep(0.5)
        driver.execute_script(f"document.querySelector(arguments[0]).click();", selector)
        return True
    except Exception as e:
        logger.warning(f"Failed to click element {repr(e)}")
        return False

def click_element_js(driver, element, scroll_first=True):
    """Click element using JavaScript with optional scrolling"""
    try:
        if scroll_first:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception as e:
        logger.warning(f"Failed to click element: {repr(e)}")
        return False

def safe_click(driver, element=None, selector=None, element_id=None, scroll_first=True, timeout=3):
    """Safe click with multiple fallback methods"""
    try:
        # Method 1: Click by ID if provided
        if element_id:
            if click_by_id(driver, element_id, scroll_first):
                return True
        
        # Method 2: Click by selector if provided
        if selector:
            if click_by_selector(driver, selector, scroll_first):
                return True
        
        # Method 3: Click element directly if provided
        if element:
            if click_element_js(driver, element, scroll_first):
                return True
        
        # If all methods failed
        logger.error("All click methods failed")
        return False
        
    except Exception as e:
        logger.error(f"Safe click failed: {repr(e)}")
        return False

# Common Amazon-specific click functions
def click_amazon_button(driver, button_id):
    """Click common Amazon buttons with fallback methods"""
    amazon_buttons = {
        "continue": ["#continue", "#continue-announce", "[name='continue']"],
        "submit": ["#signInSubmit", "[type='submit']", ".a-button-input"],
        "create_account": ["#createAccountSubmit", "#register_accordion_header"],
        "verify": ["input[aria-label='Verify OTP Button']", "#cvf-submit-otp-button"],
        "skip": ["#ap-account-fixup-phone-skip-link", ".a-link-normal"]
    }
    
    if button_id in amazon_buttons:
        selectors = amazon_buttons[button_id]
        for selector in selectors:
            if click_by_selector(driver, selector, scroll_first=True):
                logger.info(f"Successfully clicked {button_id} using selector: {selector}")
                return True
        
        logger.warning(f"Failed to click {button_id} with all selectors")
        return False
    else:
        logger.error(f"Unknown Amazon button: {button_id}")
        return False
        
def focus_input(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        driver.execute_script("arguments[0].focus();", element)
        return True
    except Exception as ex:
        logger.error(f"Focus input fail: {repr(ex)}")
        return False
    
def get_2fa_code(secret_key):
    try:
        # Loại bỏ khoảng trắng và tạo đối tượng TOTP
        totp = pyotp.TOTP(secret_key.replace(' ', ''))
        token = totp.now()
        logger.info(f"{secret_key} - {token}")
        time.sleep(10)
        return token
    except Exception as e:
        logger.error(f"Lỗi khi tạo mã 2FA: {repr(e)}")
        return None

def select_autocomplete(driver):
    try:
        # Chờ dropdown autocomplete xuất hiện
        time.sleep(random.uniform(1, 3))
        # Gửi phím DOWN và ENTER để chọn gợi ý đầu tiên
        driver.switch_to.active_element.send_keys(Keys.DOWN)
        time.sleep(random.uniform(0.1, 0.3))  # Chờ ngắn để mô phỏng hành vi người dùng
        driver.switch_to.active_element.send_keys(Keys.ENTER)
        logger.info(" Đã chọn gợi ý autocomplete cho địa chỉ")
    except Exception:
        # Nếu không có autocomplete, tiếp tục
        logger.info(" Không tìm thấy autocomplete, tiếp tục nhập địa chỉ")
def refresh_page(driver):
    driver.refresh()
    time.sleep(5)
def check_login(driver, email, password):
    try:
        is_login = False
        try:
            driver.find_element(By.ID, "ap-account-fixup-phone-skip-link")       
            click_by_id(driver, "ap-account-fixup-phone-skip-link")
        except:
            pass
        wait = WebDriverWait(driver, 15)
        # Nhập email
        email_input = wait.until(EC.visibility_of_element_located((By.ID, "ap_email")))
        human_type(email_input, email)
        is_login = True
        try:
            form_login = driver.find_element(By.CSS_SELECTOR, "form[name='signIn']")
            form_login.submit() 
        except:
            click_amazon_button(driver, "continue")
        refresh_page(driver)
        if "ap/cvf" in driver.current_url or not handle_captcha(driver, email):
            logger.error(f"🚫 CAPTCHA sau email: {email}")
            return False, "CAPTCHA"

        # Nhập mật khẩu
        try:
            pwd_input = wait.until(EC.visibility_of_element_located((By.ID, "ap_password")))
            human_type(pwd_input, password)
        except:
            if is_login:
                return False, "NO PASSWORD INPUT"
            return False, None
        try:
            form_login = driver.find_element(By.CSS_SELECTOR, "form[name='signIn']")
            form_login.submit()
        except: 
            click_amazon_button(driver, "submit")
        refresh_page(driver)
        if "ap/cvf" in driver.current_url or not handle_captcha(driver, email):
            logger.error(f"🚫 CAPTCHA sau mật khẩu: {email}")
            return False, "CAPTCHA"
        return True, None
    except Exception as e:
        # logger.error(f"❗ Lỗi khi đăng nhập tài khoản {email}: {repr(e)}")
        # traceback_str = traceback.format_exc()
        # logger.error(f"Chi tiết lỗi:\n{traceback_str}")
        return False, repr(e)

def findElement(driver, selector, backup_selector=None):
            try:
                return driver.find_element(By.CSS_SELECTOR, selector)
            except:
                try:
                    return driver.find_element(By.CSS_SELECTOR, backup_selector)
                except:
                    return None

def find_element_by_text(driver, tag, text, case_insensitive=True):
    elements = driver.find_elements(By.TAG_NAME, tag)
    text = text.strip()

    for el in elements:
        el_text = el.text.strip()
        if case_insensitive:
            if text.lower() in el_text.lower():
                return el
        else:
            if text in el_text:
                return el
    return None

# Hàm đăng ký Amazon chính
def register_amazon(email, orderid, username, sdt, address, proxy, password, shopgmail_api, address_2):
    hidemium = HidemiumAPI()

    if not email or not orderid:
        logger.error("CẢNH BÁO: Không thể tạo Gmail mới")
        return False
    time.sleep(15)
    # Tạo cấu hình mới
    profile_id = hidemium.create_profile(proxy, f"Profile_{email}")
    if not profile_id:
        logger.error(f"CẢNH BÁO: Không tạo được cấu hình cho {email}")
        return False
    
    # Khởi động trình duyệt
    profile_data = hidemium.start_profile(profile_id)
    if not profile_data:
        logger.error(f"CẢNH BÁO: Không khởi động được cấu hình cho {email}")
        hidemium.delete_profile(profile_id)
        return False
    
    
    remote_debugging_address = profile_data.get("remote_debugging_address")
    if not remote_debugging_address:
        logger.error(f"CẢNH BÁO: Không có địa chỉ gỡ lỗi từ xa cho {email}")
        hidemium.close_profile(profile_id)
        hidemium.delete_profile(profile_id)
        return False
    
    # Thiết lập Selenium với trình duyệt của GemLogin
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", remote_debugging_address)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    is_registered = False
    backup_code = ""
    try:
        wait = WebDriverWait(driver, 10)
        def handle_reg_link(start_link):
            max_retry = 5
            while max_retry > 0:
                time.sleep(5)
                try:
                    if not driver.session_id:
                        logger.error(f"Phiên làm việc gemLogin đã chết hoặc chưa được khởi tạo với {email}")
                        return False
                    driver.get(start_link)
                    time.sleep(10)

                    if "www.amazon.com/amazonprime" in start_link:
                        form = wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'form[action="/gp/prime/pipeline/membersignup"]'))
                        )
                        form.submit()
                    elif ("sellercentral.amazon.com" in start_link) and ("sellercentral.amazon.com/ap/signin" not in start_link):
                        btn_sign_ins = driver.find_elements(By.TAG_NAME, "button")
                        sign_up_btn = next((btn for btn in btn_sign_ins if btn.text.strip() == 'Sign up'), None)
                        if sign_up_btn:
                            click_element_js(driver, sign_up_btn)
                        else:
                            logger.error(f"Không tìm thấy button Sign up")
                            max_retry -= 1
                            continue
                    elif "sellercentral.amazon.ca" in start_link:
                        btn_sign_ins = driver.find_elements(By.TAG_NAME, "a")
                        sign_up_btn = next((btn for btn in btn_sign_ins if btn.text.strip() == 'Sign up'), None)
                        if sign_up_btn:
                            click_element_js(driver, sign_up_btn)
                            time.sleep(5)
                        else:
                            logger.error(f"Không tìm thấy button Sign up")
                            max_retry -= 1
                    elif "audible.com" in start_link:
                        driver.get("https://www.amazon.com/ap/signin?clientContext=135-4992534-7011834&openid.pape.max_auth_age=900&openid.return_to=https%3A%2F%2Fwww.audible.com%2F%3FloginAttempt%3Dtrue&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=audible_experiment_shared_web_us&openid.mode=checkid_setup&siteState=audibleid.userType%3Damzn%2Caudibleid.mode%3Did_res&marketPlaceId=AF2M0KC94RCEA&language=en_US&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&pageId=amzn_audible_bc_us&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
                        time.sleep(10)
                    elif "woot.com" in start_link:
                        time.sleep(10)
                        driver.get("https://auth.woot.com/ap/signin?openid.ns=http%3a%2f%2fspecs.openid.net%2fauth%2f2.0&openid.identity=http%3a%2f%2fspecs.openid.net%2fauth%2f2.0%2fidentifier_select&openid.claimed_id=http%3a%2f%2fspecs.openid.net%2fauth%2f2.0%2fidentifier_select&rmrMeStringID=ap_rememeber_me_default_message&openid.ns.pape=http%3a%2f%2fspecs.openid.net%2fextensions%2fpape%2f1.0&server=%2fap%2fsignin%3fie%3dUTF8&openid.ns.oa2=http%3a%2f%2fwww.amazon.com%2fap%2fext%2foauth%2f2&openid.oa2.client_id=device%3a70c7390e4ff54cefbda52d3b5b7fbbca&openid.oa2.response_type=code&openid.oa2.code_challenge=fthSXqjug7QpFls8kgd50cks37c6nBhN2qUqKp-wVac&openid.oa2.code_challenge_method=S256&openid.mode=checkid_setup&openid.assoc_handle=amzn_woot_desktop_us&pageId=wootgreen&openid.oa2.scope=device_auth_access&openid.return_to=https%3a%2f%2faccount.woot.com%2fauth%3freturnUrl%3dhttps%253A%252F%252Fwww.woot.com%252F%26useNewUI%3duseNewUI%253Dtrue%26rebrand2025%3drebrand2025%253Dtrue%26verificationToken%3d4c6546cd19a04e0bc7e80986e17a99da45a5cee24eb5689f4bcbdf6d3a09547e&amzn_acc=true#signin")
                        time.sleep(10)
                        driver.get("https://na.account.amazon.com/ap/signin?_encoding=UTF8&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.pape.max_auth_age=0&ie=UTF8&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=amzn_lwa_na&marketPlaceId=ATVPDKIKX0DER&arb=c9c3d559-7857-4fd7-b6a7-edefe01c3728&language=en_US&openid.return_to=https%3A%2F%2Fna.account.amazon.com%2Fap%2Foa%3FmarketPlaceId%3DATVPDKIKX0DER%26arb%3Dc9c3d559-7857-4fd7-b6a7-edefe01c3728%26language%3Den_US&enableGlobalAccountCreation=1&metricIdentifier=amzn1.application.1a921404150f44eb8a14f7c2bfa2f008&signedMetricIdentifier=%2B2kJ4QB725KTB%2FdrD%2B0wLJD5sjO9%2FG83I1jto1ql4D0%3D")
                        time.sleep(10)
                    elif "zappos.com" in start_link:
                        driver.get("https://www.zappos.com/federated-login")
                        time.sleep(10)
                        driver.get("https://na.account.amazon.com/ap/signin?_encoding=UTF8&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.pape.max_auth_age=0&ie=UTF8&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&pageId=lwa&openid.assoc_handle=amzn_lwa_na&marketPlaceId=ATVPDKIKX0DER&arb=548af87d-e159-4bfb-bea9-3e3dde6d215d&language=en_US&openid.return_to=https%3A%2F%2Fna.account.amazon.com%2Fap%2Foa%3FmarketPlaceId%3DATVPDKIKX0DER%26arb%3D548af87d-e159-4bfb-bea9-3e3dde6d215d%26language%3Den_US&enableGlobalAccountCreation=1&metricIdentifier=amzn1.application.d7323c22c1f240eaa7412c7fc5d3fd64&signedMetricIdentifier=ABhE9UOwTDbtBMDGebYFKfI3vlGBXQPjrA68W9LwMO8%3D")
                        time.sleep(10)
                    elif "imdb.com" in start_link:
                        time.sleep(10)
                        driver.get("https://www.imdb.com/registration/signin/?u=%2F&ref_=hm_nv_generic_lgin")
                        time.sleep(10)
                        driver.get("https://na.account.amazon.com/ap/signin?_encoding=UTF8&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.pape.max_auth_age=0&ie=UTF8&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&pageId=lwa&openid.assoc_handle=amzn_lwa_na&marketPlaceId=ATVPDKIKX0DER&arb=64453e52-3e7d-44d2-8b18-43709bfad80d&language=en_US&openid.return_to=https%3A%2F%2Fna.account.amazon.com%2Fap%2Foa%3FmarketPlaceId%3DATVPDKIKX0DER%26arb%3D64453e52-3e7d-44d2-8b18-43709bfad80d%26language%3Den_US&enableGlobalAccountCreation=1&metricIdentifier=amzn1.application.eb539eb1b9fb4de2953354ec9ed2e379&signedMetricIdentifier=fLsotU64%2FnKAtrbZ2LjdFmdwR3SEUemHOZ5T2deI500%3D")
                        time.sleep(10)
                    elif "goodreads.com/" in start_link:
                        # select a element with text "Continue with Amazon"
                        time.sleep(10)
                        try: 
                            amazon_link = driver.find_element(By.XPATH, "//a[contains(text(), 'Continue with Amazon')]")
                            click_by_selector(driver, "a")
                        except:
                            driver.get("https://na.account.amazon.com/ap/signin?_encoding=UTF8&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.pape.max_auth_age=0&ie=UTF8&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&pageId=lwa&openid.assoc_handle=amzn_lwa_na&marketPlaceId=ATVPDKIKX0DER&arb=2e316644-b806-481e-9f63-2208d3c97967&language=en_US&openid.return_to=https%3A%2F%2Fna.account.amazon.com%2Fap%2Foa%3FmarketPlaceId%3DATVPDKIKX0DER%26arb%3D2e316644-b806-481e-9f63-2208d3c97967%26language%3Den_US&enableGlobalAccountCreation=1&metricIdentifier=amzn1.application.7ff8a2be5dae490b9914b4f430ca5c4c&signedMetricIdentifier=pjdsmDnaXhj%2FNbw9hCvWIQvTgX0htu%2BjAbCBVOtDWHM%3D")
                            time.sleep(10)
                    elif "luna.amazon.com/" in start_link:
                        try: 
                            time.sleep(10)
                            driver.get("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=3600&openid.return_to=https%3A%2F%2Fluna.amazon.com%2Flibrary&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=tempo_us&openid.mode=checkid_setup&language=en_US&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
                        except:
                            driver.get("https://www.amazon.com/ap/signin?openid.pape.max_auth_age=3600&openid.return_to=https%3A%2F%2Fluna.amazon.com%2F&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=tempo_us&openid.mode=checkid_setup&language=en_US&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
                        time.sleep(10)
                    
                    click_by_id(driver, "createAccountSubmit")
                    time.sleep(5)
                    # # Chọn Tạo tài khoản
                    # wait.until(EC.presence_of_element_located((By.ID, "register_accordion_header")))
                    # click_by_id(driver, "register_accordion_header")
                    # Điền biểu mẫu đăng ký
                    name_field = wait.until(EC.presence_of_element_located((By.ID, "ap_customer_name")))
                    focus_input(driver, name_field)
                    human_type(name_field, username)
                    
                    email_field = driver.find_element(By.ID, "ap_email")
                    focus_input(driver, email_field)
                    human_type(email_field, email)
                    
                    # password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                    # password = "123456aA@Sang"
                    password_field = driver.find_element(By.ID, "ap_password")
                    click_by_id(driver, "ap_password")
                    time.sleep(3)
                    human_type(password_field, password)

                    repeat_password_field = driver.find_element(By.ID, "ap_password_check")
                    focus_input(driver, repeat_password_field)
                    human_type(repeat_password_field, password)

                    try:
                        register_form = driver.find_element(By.ID, "ap_register_form")
                        register_form.submit()
                    except:
                        click_amazon_button(driver, "continue")
                    
                    # Kiểm tra CAPTCHA
                    if not handle_captcha(driver, email):
                        log_failed_account(email, "captcha.txt")
                        return False
                    return True
                except Exception:
                    max_retry -= 1
            if max_retry == 0:
                return False
        
        start_links = read_file("reg_link.txt")
        check = False
        for start_link in start_links:
            if handle_reg_link(start_link):
                check = True
                break
            time.sleep(random.uniform(1, 3))
        if not check:
            logger.error(f"CẢNH BÁO: Không tạo được tài khoản cho {email}")
            increment_failed_account_creation()
            log_failed_account(email, "captcha.txt")
            return False
        otp_check = findElement(driver, "input[aria-label='Verify OTP Button']", "#verification-code-form")
        if otp_check:
            # Lấy OTP để xác minh Gmail
            otp = shopgmail_api.get_otp(orderid)
            if not otp:
                logger.error(f"CẢNH BÁO: Không lấy được OTP cho {email}")
                log_failed_account(email, "captcha.txt")
                return False
            otp_field = wait.until(EC.presence_of_element_located((By.ID, "cvf-input-code")))
            human_type(otp_field, otp)
            try:
                time.sleep(5)
                verify_form = driver.find_element(By.ID, "verification-code-form") 
                verify_form.submit()
                
            except:
                click_by_selector(driver, "input[aria-label='Verify OTP Button']")
            time.sleep(10)
        else: 
            time.sleep(5)
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        time.sleep(5)
        def check_phone_verification(driver, email):
            """Check if account is blocked by phone verification and log appropriate message"""
            try:
                
                phone_verification_checks = [
                    (lambda: driver.current_url.startswith("https://www.amazon.com/ap/cvf/verify"), "US"),
                    (lambda: driver.current_url.startswith("https://www.amazon.ca/ap/accountfixup"), "CA")
                ]
                for check_func, region in phone_verification_checks:
                    if check_func():
                        logger.error(f"CẢNH BÁO: {email} dính sdt {region}")
                        return False
                
                return True
            except Exception as e:
                logger.error(f"Lỗi khi kiểm tra phone verification cho {email}: {repr(e)}")
                return True

        # Replace the selection with:
        if not check_phone_verification(driver, email):
            return False
        
        is_registered = True
        # Điều hướng đến thiết lập 2FA
        time.sleep(5)
        driver.get("https://www.amazon.ca/ap/signin?openid.pape.max_auth_age=900&openid.return_to=https%3A%2F%2Fwww.amazon.ca%2Fap%2Fcnep%3Fie%3DUTF8%26orig_return_to%3Dhttps%253A%252F%252Fwww.amazon.ca%252Fyour-account%26openid.assoc_handle%3Dcaflex%26pageId%3Dcaflex&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=caflex&openid.mode=checkid_setup&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")
        time.sleep(5)
        refresh_page(driver)
        status, error = check_login(driver, email, password)
        if error is not None and error == "NO PASSWORD INPUT":
            logger.error(f"CẢNH BÁO: {email} dính sdt US sau khi nhập otp")
        time.sleep(10)
        # ap-account-fixup-phone-skip-link
        try:
            click_by_id(driver, "ap-account-fixup-phone-skip-link")
        except:
            pass
        time.sleep(5)
        # Kích hoạt 2FA
        driver.get("https://www.amazon.ca/a/settings/approval/setup/register?openid.mode=checkid_setup&ref_=ax_am_landing_add_2sv&openid.assoc_handle=anywhere_v2_ca&openid.ns=http://specs.openid.net/auth/2.0")
        time.sleep(5)  # Wait for the page to load
        try:
            skip = driver.find_element(By.ID, "ap-account-fixup-phone-skip-link")       
            click_by_id(driver, "ap-account-fixup-phone-skip-link")
        except:
            refresh_page(driver)
        def input_otp():
            form_otp_check = findElement(driver, "#verification-code-form", "#input-box-otp")
            if form_otp_check:
                otp_field_2fa = findElement(driver, "#input-box-otp", "form input")
                otp_2fa = shopgmail_api.get_otp(orderid)
                if not otp_2fa:
                    logger.error(f"CẢNH BÁO: Không lý OTP 2FA cho {email}")
                    log_failed_account(email, "captcha.txt")
                    return False
                human_type(otp_field_2fa, otp_2fa)
                formConfirm = wait.until(EC.presence_of_element_located((By.ID, "verification-code-form")))
                formConfirm.submit()
            # Confirm button enable-mfa-form-submit
            try: 
                enable_chechbox = wait.until(EC.presence_of_element_located((By.NAME, "trustThisDevice")))
                click_by_selector(driver, "[name='trustThisDevice']")
                enable_2fa_form = wait.until(EC.presence_of_element_located((By.ID, "enable-mfa-form")))
                enable_2fa_form.submit()
            except:
                pass
        input_otp()
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        
        # Id cvf-submit-otp-button
        wait.until(EC.presence_of_element_located((By.ID, "sia-otp-accordion-totp-header")))
        click_by_id(driver, "sia-otp-accordion-totp-header")
        # get sia-auth-app-formatted-secret
        backup_code = driver.execute_script(
            "return document.getElementById('sia-auth-app-formatted-secret').textContent.trim();"
        )
        
        # get 2fa OTP code from secret
        otp_2fa = get_2fa_code(backup_code)
        if not otp_2fa:
            logger.error(f"CẢNH BÁO: Không lấy được OTP 2FA cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        
        otp_field_2fa = wait.until(EC.presence_of_element_located((By.ID, "ch-auth-app-code-input")))
        human_type(otp_field_2fa, otp_2fa)
        click_by_id(driver, "ch-auth-app-submit")
        time.sleep(5)
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        input_otp()
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        time.sleep(5)
        input_otp()
        time.sleep(5)
        driver.get("https://www.amazon.ca/ax/account/manage")
        time.sleep(10)
        driver.get("https://www.amazon.ca/cpe/yourpayments/settings/manageoneclick")
        time.sleep(5)
        try:
            add_btn = driver.find_element(By.CSS_SELECTOR, '[name="ppw-widgetEvent:AddOneClickEvent:{}"]')
            if add_btn:
                click_by_selector(driver, '[name="ppw-widgetEvent:AddOneClickEvent:{}"]')
                time.sleep(5)
                add_name, city, state, zipcode = address.split("|")

                full_name_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-fullName"]')
                focus_input(driver, full_name_field)
                human_type(full_name_field, username)

                address_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-line1"]')
                focus_input(driver, address_field)
                human_type(address_field, add_name)

                city_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-city"]')
                focus_input(driver, city_field)
                human_type(city_field, city)

                state_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-stateOrRegion"]')
                focus_input(driver, state_field)
                human_type(state_field, state)

                zipcode_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-postalCode"]')
                focus_input(driver, zipcode_field)
                human_type(zipcode_field, zipcode)

                phone_field = driver.find_element(By.CSS_SELECTOR, '[name="ppw-phoneNumber"]')
                focus_input(driver, phone_field)
                human_type(phone_field, sdt)

                time.sleep(3)
                try:
                    label = driver.find_element(By.CSS_SELECTOR, ".a-dropdown-prompt")
                    select_element = driver.find_element(By.NAME, "ppw-countryCode")
                    driver.execute_script("arguments[0].innerText = 'United States';", label)
                    driver.execute_script("arguments[0].value = 'US';", select_element)
                except Exception as e:
                    pass
                finally:
                    time.sleep(3)

                def submit_add():
                    try:
                        continue_btn = driver.find_element(By.CSS_SELECTOR, '[name="ppw-widgetEvent:AddAddressEvent"]')
                        click_by_selector(driver, '[name="ppw-widgetEvent:AddAddressEvent"]')
                    except:
                        form = driver.find_element(By.CSS_SELECTOR, "form.pmts-portal-component")
                        form.submit()
                    time.sleep(5)

                
                submit_add()
                time.sleep(10)
                check_error = driver.find_elements(By.CSS_SELECTOR, "h4.a-alert-heading")
                found_error = False
                for el in check_error:
                    if el.text.strip() == "There was a problem.":
                        found_error = True
                        break
                if found_error:
                    submit_add()
                    time.sleep(10)
            else:
                logger.error(f"CẢNH BÁO: Không tìm thấy nút thêm địa chỉ thanh toán cho {email}")
                log_failed_account(email, "chua_add.txt")
                return False
        except Exception as e:
            log_failed_account(email, "chua_add.txt")
            return False

        # # Lưu tài khoản thành công
        save_account(email, password, backup_code)
        # logger.info(f" Đăng ký thành công {email}. Thực hiện click logo.")
        time.sleep(5)
        try:
            driver.get("https://www.amazon.ca/gp/bestsellers/?ref_=navm_em_bestsellers_0_1_1_2")
            time.sleep(5)
            links = driver.find_elements(By.CSS_SELECTOR, "a.a-link-normal")
            if  len(links) > 0:
                random_link = random.choice(links)
                click_by_selector(driver, "a.a-link-normal")
                time.sleep(5)
        except:
            item_links = read_link_sp_canada()
            random_item = random.choice(item_links)
            driver.get(random_item)
        time.sleep(15)
        return True
    except Exception as e:
        logger.error(f"CẢNH BÁO: Lỗi khi xử lý {email}: {str(e)}\n{traceback.format_exc()}")
        log_failed_account(email, "captcha.txt")
        return False
    finally:
        driver.close()
        hidemium.close_profile(profile_id)
        if is_registered: 
            save_account(email, password, backup_code, "account_created.txt")
        # if not hidemium.delete_profile(profile_id):
        #     logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id} cho {email}")


def register_and_cleanup(i, email, orderid, username, sdt, address, proxy, password, api, address_2):
    try:
        success = register_amazon(email, orderid, username, sdt, address, proxy, password, api, address_2)
        if success:
            remove_line("username.txt", i)
            remove_line("sdt.txt", i)
            remove_line("add.txt", i)
            remove_line("password.txt", i)
    except Exception as e:
        logger.error(f"Lỗi xử lý tài khoản {i}: {e}")

def check_pause():
    while pause_event.is_set():
        time.sleep(60)

def worker(index, proxy, username, sdt, address, password, shopgmail_api, address_2):
    try:
        threading.current_thread().name = f"{index + 1}"
        check_pause()
        # Tạo Gmail
        while True:
            try:
                # Kiểm tra pause event trong quá trình tạo Gmail
                check_pause()
                email, orderid = shopgmail_api.create_gmail_account()
                if email and orderid:
                    break
                time.sleep(random.uniform(1, 3))
            except Exception:
                time.sleep(random.uniform(1, 3))

        # Gọi hàm xử lý
        register_and_cleanup(index, email, orderid, username, sdt, address, proxy, password, shopgmail_api, address_2)

    except Exception as e:
        logger.error(f"Lỗi ở luồng {index}: {e}")
def check_stop_key(task_queue):
    threading.current_thread().name = "Dừng"
    while not stop_event.is_set():
        key = input()
        if key.strip().lower() == "x":
            logger.warning("ĐÃ TẮT HẾT LUỒNG CHƯA CHẠY")
            stop_event.set()
            with task_queue.mutex:
                task_queue.queue.clear()
            break
def worker_from_queue(task_queue):
    while True:
        try:
            # Kiểm tra pause event trước khi lấy task mới
            check_pause()
            task = task_queue.get(timeout=0.5)
        except Empty:
            if stop_event.is_set():
                break
            continue
        if task is None:  # tín hiệu kết thúc
            task_queue.task_done()
            break
        func, args = task
        func(*args)
        task_queue.task_done()
# Hàm chính
def main():
    # Nhập API key và số lượng tài khoản
    logger.info(" Đang kiểm tra apikey api.shopgmail9999.com")
    apikey = read_file("apikey.txt")
    if not apikey:
        logger.error("CẢNH BÁO: Không tìm thấy apikey. Vui lý nhập apikey.txt")
        return
    logger.info(f"API key: {apikey}")
    try:
        num_accounts = int(input("🔢 Nhập số tài khoản cần tạo: "))
        max_threads = int(input("⚙️ Nhập số luồng chạy mỗi lần: "))
        global max_failed_account_creation
        max_failed_account_creation = int(input("🚫 Nhập số lỗi tối đa trước khi tạm dừng 1 giờ: "))
    except ValueError:
        logger.error("❌ Giá trị nhập vào không hợp lệ. Vui lòng nhập số nguyên.")
        return
    
    # Khởi tạo ShopGmailAPI
    shopgmail_api = ShopGmailAPI(apikey)
    
    # Tải tệp đầu vào
    usernames = read_file("username.txt")
    sdts = read_file("sdt.txt")
    addresses = read_file("add.txt")
    proxies = read_file("proxy.txt")
    passwords = read_file("password.txt")
    
    # Đảm bảo đủ đầu vào
    min_length = min(len(usernames), len(sdts), len(addresses), len(passwords), num_accounts)
    if min_length == 0:
        logger.error("❌ Dữ liệu đầu vào không đủ để xử lý.")
        return
    max_threads = min(max_threads, min_length)
    logger.info(f"🔧 Sẽ xử lý {min_length} tài khoản với {max_threads} luồng")
    logger.info(f"🚫 Sẽ tạm dừng 1 giờ khi đạt {max_failed_account_creation} lỗi tạo tài khoản")
    logger.info("💡 Nhấn phím 'x' rồi Enter để dừng việc tạo tài khoản mới, nhưng vẫn để các luồng đang chạy hoàn tất.")

    task_queue = Queue()

    threading.Thread(target=check_stop_key, args=(task_queue,), daemon=True).start()

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        for _ in range(max_threads):
            executor.submit(worker_from_queue, task_queue)

        for i in range(min_length):
            if stop_event.is_set():
                break
            check_pause()
            proxy = proxies[i % len(proxies)].strip() if proxies else ""
            # random address_2 != i
            address_2 = addresses[i + 1] if i + 1 < len(addresses) else addresses[0]
            task_queue.put((worker, (i, proxy, usernames[i], sdts[i], addresses[i], passwords[i], shopgmail_api, address_2)))
            time.sleep(1)

        while not task_queue.empty() and not stop_event.is_set():
            time.sleep(0.1)

        for _ in range(max_threads):
            task_queue.put(None)

    logger.info("🎉 Hoàn tất xử lý toàn bộ tài khoản.")

if __name__ == "__main__":
    main()