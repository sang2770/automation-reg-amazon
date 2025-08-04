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

service = Service(ChromeDriverManager(driver_version="137.0.7151.122").install())
stop_event = threading.Event()

# Hàm đọc config.json
def read_config(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"CẢNH BÁO: Không tìm thấy tệp {file_path}. Chạy mà không dùng dữ liệu từ tệp.")
        return {}

config = read_config("config.json")

# GemLogin API client
class GemLoginAPI:
    def __init__(self):
        self.base_url = getattr(config, "gem_login_server", "http://localhost:1010")
        self.session = requests.Session()

    def create_profile(self, proxy, profile_name="AmazonProfile"):
        # Tạo cấu hình mới với proxy SOCKS5 và hệ điều hành Android
        payload = {
            "profile_name": f"{profile_name}_{random.randint(1000, 9999)}",
            "group_name": "All",
            "raw_proxy": f"socks5://{proxy}",
            "startup_urls": getattr(config, "reg_link", "https://www.amazon.com/amazonprime"),
            "is_noise_canvas": False,
            "is_noise_webgl": False,
            "is_noise_client_rect": False,
            "is_noise_audio_context": True,
            "is_random_screen": False,
            "is_masked_webgl_data": True,
            "is_masked_media_device": True,
            "os": {"type": "Android", "version": "14"},
            "webrtc_mode": 2,
            "browser_version": "137",
            "browser_type": "chrome",
            "language": "en",
            "time_zone": "America/New_York",
            "country": "United States",
        }
        response = self.session.post(f"{self.base_url}/api/profiles/create", json=payload)
        if response.status_code == 200 and response.json().get("success"):
            return response.json().get("data", {}).get("id")
        logger.error(f"CẢNH BÁO: Không tạo được cấu hình với proxy {proxy}")
        return None

    def start_profile(self, profile_id):
        # Khởi động trình duyệt cho cấu hình
        response = self.session.get(f"{self.base_url}/api/profiles/start/{profile_id}")
        if response.status_code == 200 and response.json().get("success"):
            return response.json().get("data", {})
        logger.error(f"CẢNH BÁO: Không khởi động được cấu hình {profile_id}")
        return None

    def close_profile(self, profile_id):
        # Đóng trình duyệt
        self.session.get(f"{self.base_url}/api/profiles/close/{profile_id}")

    def delete_profile(self, profile_id):
        # Xóa cấu hình
        # response = self.session.get(f"{self.base_url}/api/profiles/delete/{profile_id}")
        # if response.status_code == 200 and response.json().get("success"):
        #     return True
        # logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id} {response.json().get('message')}")
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
            logger.warning(f"CẢNH BÁO: Lỗi khi gọi API CreateOrder: {str(e)}. Tiến hành tạo lại...")
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
    for i, char in enumerate(text):  # ✅ SỬA chỗ này
        element.send_keys(char)
        if i % random.randint(3, 7) == 0:
            time.sleep(random.uniform(0.5, 1.0))  # Nghỉ lâu hơn
        else:
            time.sleep(random.uniform(0.2, 0.4))  # Gõ chậm hơn bình thường
    time.sleep(random.uniform(2, 3))

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

def click_element(driver, element, timeout=10):
    try:
        time.sleep(2)
        element.click()
    except TimeoutException:
        logger.error("Timeout chờ element có thể click")
    except Exception as ex:
        # Scroll element vào giữa màn hình
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        # Click bằng JS
        driver.execute_script("arguments[0].click();", element)

def get_2fa_code(secret_key):
    try:
        # Loại bỏ khoảng trắng và tạo đối tượng TOTP
        totp = pyotp.TOTP(secret_key.replace(' ', ''))
        token = totp.now()
        logger.info(f"{secret_key} - {token}")
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

def check_login(driver, email, password):
    try:
        wait = WebDriverWait(driver, 15)
        # Nhập email
        email_input = wait.until(EC.visibility_of_element_located((By.ID, "ap_email_login")))
        human_type(email_input, email)
        try:
            form_login = driver.find_element(By.CSS_SELECTOR, "form[name='signIn']")
            form_login.submit() 
        except:
            click_element(driver, driver.find_element(By.ID, "continue-announce"))

        time.sleep(3)
        if "ap/cvf" in driver.current_url or handle_captcha(driver, email):
            logger.error(f"🚫 CAPTCHA sau email: {email}")
            return False, "CAPTCHA"

        # Nhập mật khẩu
        pwd_input = wait.until(EC.visibility_of_element_located((By.ID, "ap_password")))
        human_type(pwd_input, password)
        try:
            form_login = driver.find_element(By.CSS_SELECTOR, "form[name='signIn']")
            form_login.submit()
        except: 
            click_element(driver, driver.find_element(By.ID, "signInSubmit"))

        time.sleep(5)
        if "ap/cvf" in driver.current_url or handle_captcha(driver, email):
            logger.error(f"🚫 CAPTCHA sau mật khẩu: {email}")
            return False, "CAPTCHA"
        return True, None
    except Exception as e:
        logger.error(f"❗ Lỗi khi đăng nhập tài khoản {email}: {repr(e)}")
        traceback_str = traceback.format_exc()
        logger.debug(f"Chi tiết lỗi:\n{traceback_str}")
        return False, repr(e)
# Hàm đăng ký Amazon chính
def register_amazon(email, orderid, username, sdt, address, proxy, password, shopgmail_api):
    gemlogin = GemLoginAPI()

    if not email or not orderid:
        logger.error("CẢNH BÁO: Không thể tạo Gmail mới")
        return False
    time.sleep(15)
    # Tạo cấu hình mới
    profile_id = gemlogin.create_profile(proxy, f"Profile_{email}")
    if not profile_id:
        logger.error(f"CẢNH BÁO: Không tạo được cấu hình cho {email}")
        return False
    
    # Khởi động trình duyệt
    profile_data = gemlogin.start_profile(profile_id)
    if not profile_data:
        logger.error(f"CẢNH BÁO: Không khởi động được cấu hình cho {email}")
        gemlogin.delete_profile(profile_id)
        return False
    
    
    remote_debugging_address = profile_data.get("remote_debugging_address")
    if not remote_debugging_address:
        logger.error(f"CẢNH BÁO: Không có địa chỉ gỡ lỗi từ xa cho {email}")
        gemlogin.close_profile(profile_id)
        gemlogin.delete_profile(profile_id)
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
                            # sign_up_btn.click()
                            click_element(driver, sign_up_btn)
                        else:
                            logger.error(f"Không tìm thấy button Sign up")
                            max_retry -= 1
                            continue
                    elif "sellercentral.amazon.ca" in start_link:
                        btn_sign_ins = driver.find_elements(By.TAG_NAME, "a")
                        sign_up_btn = next((btn for btn in btn_sign_ins if btn.text.strip() == 'Sign up'), None)
                        if sign_up_btn:
                            click_element(driver, sign_up_btn)
                        else:
                            logger.error(f"Không tìm thấy button Sign up")
                            max_retry -= 1
                    # Chọn Tạo tài khoản
                    create_account_button = wait.until(EC.presence_of_element_located((By.ID, "register_accordion_header")))
                    click_element(driver, create_account_button)
                    # Điền biểu mẫu đăng ký
                    name_field = wait.until(EC.presence_of_element_located((By.ID, "ap_customer_name")))
                    click_element(driver, name_field)
                    time.sleep(3)
                    human_type(name_field, username)
                    
                    email_field = driver.find_element(By.ID, "ap_email")
                    click_element(driver, email_field)
                    time.sleep(3)
                    human_type(email_field, email)
                    
                    # password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                    # password = "123456aA@Sang"
                    password_field = driver.find_element(By.ID, "ap_password")
                    click_element(driver, password_field)
                    time.sleep(3)
                    human_type(password_field, password)

                    try:
                        register_form = driver.find_element(By.ID, "ap_register_form")
                        register_form.submit()
                    except:
                        click_element(driver, driver.find_element(By.ID, "continue"))
                    
                    # Kiểm tra CAPTCHA
                    if not handle_captcha(driver, email):
                        log_failed_account(email, "captcha.txt")
                        return False
                    return True
                except Exception:
                    max_retry -= 1
            if max_retry == 0:
                logger.error(f"CẢNH BÁO: Không tạo được tài khoản cho {email}")
                log_failed_account(email, "captcha.txt")
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
            log_failed_account(email, "captcha.txt")
            return False
        # Lấy OTP để xác minh Gmail
        otp = shopgmail_api.get_otp(orderid)
        if not otp:
            logger.error(f"CẢNH BÁO: Không lấy được OTP cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        
        otp_field = wait.until(EC.presence_of_element_located((By.ID, "cvf-input-code")))
        human_type(otp_field, otp)
        try:
            verify_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='Verify OTP Button']")))
            click_element(driver, verify_button)
        except:
            verify_form = driver.find_element(By.ID, "verification-code-form") 
            verify_form.submit()
        time.sleep(10)
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        
        # Điều hướng đến thiết lập 2FA
        driver.get(getattr(config, "2fa_amazon_link", "https://www.amazon.com/ax/account/manage?openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fyour-account%3Fref_%3Dya_cnep&openid.assoc_handle=anywhere_v2_us&shouldShowPasskeyLink=true&passkeyEligibilityArb=23254432-b9cb-4b93-98b6-ba9ed5e45a65&passkeyMetricsActionId=07975eeb-087d-42ab-971d-66c2807fe4f5"))
        time.sleep(10)
        if "www.amazon.com/ax/account/manage" not in driver.current_url and "amazon.com/ap/signin" in driver.current_url:
            login_success, error_reason = check_login(driver, email, password)
            if not login_success:
                logger.error(f"Đăng nhập thất bại cho tài khoản {email}: {error_reason}")
                log_failed_account(email, "captcha.txt")
                return False
            time.sleep(10)
            # ap-account-fixup-phone-skip-link
            try:
                skip = driver.find_element(By.ID, "ap-account-fixup-phone-skip-link")       
                click_element(driver, skip)
            except:
                if "www.amazon.com/ax/account/manage" not in driver.current_url:
                    driver.get("https://www.amazon.com/ax/account/manage?openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fyour-account%3Fref_%3Dya_cnep&openid.assoc_handle=anywhere_v2_us&shouldShowPasskeyLink=true&passkeyEligibilityArb=23254432-b9cb-4b93-98b6-ba9ed5e45a65&passkeyMetricsActionId=07975eeb-087d-42ab-971d-66c2807fe4f5")
            time.sleep(10)
        # Kích hoạt 2FA
        is_registered = True
        turn_on_2fa = driver.find_element(By.ID, "TWO_STEP_VERIFICATION_BUTTON")
        try: 
            turn_on_2fa.click()
        except Exception as e:
            click_element(driver, turn_on_2fa)
        time.sleep(5)  # Wait for the page to load
        # get OTP again
        otp_2fa = shopgmail_api.get_otp(orderid)
        if not otp_2fa:
            logger.error(f"CẢNH BÁO: Không lý OTP 2FA cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        def findElement(driver, selector, backup_selector=None):
            try:
                return driver.find_element(By.CSS_SELECTOR, selector)
            except NoSuchElementException:
                if backup_selector:
                    return driver.find_element(By.CSS_SELECTOR, backup_selector)
                return None
            
        otp_field_2fa = findElement(driver, "#input-box-otp", "form input")

        human_type(otp_field_2fa, otp_2fa)
        formConfirm =  wait.until(EC.presence_of_element_located((By.ID, "verification-code-form")))
        formConfirm.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        
        # Id cvf-submit-otp-button
        section_otp = wait.until(EC.presence_of_element_located((By.ID, "sia-otp-accordion-totp-header")))
        click_element(driver, section_otp)
        # get sia-auth-app-formatted-secret
        backup_code = driver.find_element(By.ID, "sia-auth-app-formatted-secret").text
        
        # get 2fa OTP code from secret
        otp_2fa = get_2fa_code(backup_code)
        if not otp_2fa:
            logger.error(f"CẢNH BÁO: Không lấy được OTP 2FA cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        
        otp_field_2fa = wait.until(EC.presence_of_element_located((By.ID, "ch-auth-app-code-input")))
        human_type(otp_field_2fa, otp_2fa)
        formConfirm =  wait.until(EC.presence_of_element_located((By.ID, "sia-add-auth-app-form")))
        formConfirm.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False

        # Confirm button enable-mfa-form-submit
        enable_chechbox = wait.until(EC.presence_of_element_located((By.NAME, "trustThisDevice")))
        click_element(driver, enable_chechbox)
        enable_2fa_form = wait.until(EC.presence_of_element_located((By.ID, "enable-mfa-form")))
        enable_2fa_form.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False

        
        # Điều hướng đến sổ địa chỉ
        driver.get(getattr(config, "amazon_add_link","https://www.amazon.com/a/addresses"))
        time.sleep(10)
        driver.get(getattr(config, "amazon_add_link","https://www.amazon.com/a/addresses/add?ref=ya_address_book_add_button"))
        time.sleep(10)
        # Thêm địa chỉ
        try:
            address_field = driver.find_element(By.ID, "address-ui-widgets-enterAddressFullName")
            human_type(address_field, username)
            
            phone_field = driver.find_element(By.ID, "address-ui-widgets-enterAddressPhoneNumber")
            human_type(phone_field, sdt)
            
            address_lines = address.split(", ")
            human_type(driver.find_element(By.ID, "address-ui-widgets-enterAddressLine1"), address_lines[0])
            select_autocomplete(driver)
            if len(address_lines) > 1:
                driver.find_element(By.ID, "address-ui-widgets-enterAddressLine2").send_keys(address_lines[1])
            # submit form address-ui-address-form
            formConfirm =  WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "address-ui-address-form")))
            formConfirm.submit()
            
            # Kiểm tra CAPTCHA lần nữa
            if not handle_captcha(driver, email):
                log_failed_account(email, "captcha.txt")
                return False
            
            # # Lưu tài khoản thành công
            save_account(email, password, backup_code)
            logger.info(f" Đăng ký thành công {email}. Thực hiện click logo.")
            try:
                logo = driver.find_element(By.ID, "nav-logo")
                click_element(driver, logo)
            except:
                driver.get("https://www.amazon.com/ref=navm_hdr_logo")
            time.sleep(5)
            item_selects = driver.find_elements(By.CSS_SELECTOR, '#desktop-grid-2 .a-link-normal')
            if len(item_selects) == 0:
                item_selects = driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]')
            if len(item_selects) > 3:
                click_element(driver, item_selects[3])
            elif len(item_selects) > 2:
                click_element(driver, item_selects[2])
            elif len(item_selects) > 1:
                click_element(driver, item_selects[1])
            elif len(item_selects) > 0:
                click_element(driver, item_selects[0])
            else:
                driver.get("https://www.amazon.com/b/?ie=UTF8&node=19277531011&ref_=af_gw_quadtopcard_f_july_xcat_cml_1&pd_rd_w=Z5OwE&content-id=amzn1.sym.28c8c8b7-487d-484e-96c7-4d7d067b06ed&pf_rd_p=28c8c8b7-487d-484e-96c7-4d7d067b06ed&pf_rd_r=J2YGJMS1OWWSAF1TRRA8&pd_rd_wg=RP51i&pd_rd_r=10053101-20a0-4a52-9465-faf1daa6535e")
            time.sleep(15)
            return True
        except Exception as e:
            logger.error(f"CẢNH BÁO: Thêm địa chỉ thất bại cho {email}: {str(e)}")
            log_failed_account(email + "|" + password + "|" + backup_code, "chua_add.txt")
            return False
    except Exception as e:
        logger.error(f"CẢNH BÁO: Lỗi khi xử lý {email}: {str(e)}\n{traceback.format_exc()}")
        log_failed_account(email, "captcha.txt")
        return False
    finally:
        driver.close()
        gemlogin.close_profile(profile_id)
        if is_registered: 
            save_account(email, password, backup_code, "account_created.txt")
        # if not gemlogin.delete_profile(profile_id):
        #     logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id} cho {email}")


def register_and_cleanup(i, email, orderid, username, sdt, address, proxy, password, api):
    try:
        success = register_amazon(email, orderid, username, sdt, address, proxy, password, api)
        if success:
            remove_line("username.txt", i)
            remove_line("sdt.txt", i)
            remove_line("add.txt", i)
            remove_line("password.txt", i)
    except Exception as e:
        logger.error(f"Lỗi xử lý tài khoản {i}: {e}")



def worker(index, proxy, username, sdt, address, password, shopgmail_api):
    try:
        threading.current_thread().name = f"{index + 1}"

        # Tạo Gmail
        while True:
            try:
                email, orderid = shopgmail_api.create_gmail_account()
                if email and orderid:
                    break
                time.sleep(random.uniform(1, 3))
            except Exception:
                time.sleep(random.uniform(1, 3))

        # Gọi hàm xử lý
        register_and_cleanup(index, email, orderid, username, sdt, address, proxy, password, shopgmail_api)

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
    logger.info("💡 Nhấn phím 'x' rồi Enter để dừng việc tạo tài khoản mới, nhưng vẫn để các luồng đang chạy hoàn tất.")

    task_queue = Queue()

    threading.Thread(target=check_stop_key, args=(task_queue,), daemon=True).start()

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        for _ in range(max_threads):
            executor.submit(worker_from_queue, task_queue)

        for i in range(min_length):
            if stop_event.is_set():
                break
            proxy = proxies[i % len(proxies)].strip() if proxies else ""
            task_queue.put((worker, (i, proxy, usernames[i], sdts[i], addresses[i], passwords[i], shopgmail_api)))
            time.sleep(1)

        while not task_queue.empty() and not stop_event.is_set():
            time.sleep(0.1)

        for _ in range(max_threads):
            task_queue.put(None)

    logger.info("🎉 Hoàn tất xử lý toàn bộ tài khoản.")

if __name__ == "__main__":
    main()