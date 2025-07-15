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
from selenium.common.exceptions import TimeoutException, WebDriverException
import traceback
import threading

service = Service(ChromeDriverManager(driver_version="135.0.7049.95").install())

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
            "browser_version": "135",
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
        response = self.session.get(f"{self.base_url}/api/profiles/delete/{profile_id}")
        if response.status_code == 200 and response.json().get("success"):
            return True
        logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id} {response.json().get('message')}")
        return False

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
                        logger.info(f"THÔNG TIN: Tạo Gmail thành công: {email} (Order ID: {orderid})")
                        return email, orderid
                    else:
                        logger.warning("CẢNH BÁO: Không tìm thấy email hoặc orderid trong phản hồi API")
                        return None, None
                else:
                    logger.warning(f"CẢNH BÁO: Lỗi khi tạo Gmail: {data.get('msg')}")
                    return None, None
            else:
                logger.error(f"CẢNH BÁO: Lỗi khi gọi API CreateOrder: {response.status_code} - {response.text}")
                return None, None
        except Exception as e:
            logger.error(f"CẢNH BÁO: Lỗi khi gọi API CreateOrder: {str(e)}")
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
            for _ in range(30):  # Thử tối đa 30 lần, cách nhau 5 giây
                response = self.session.get(api_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success" and data.get("data", {}).get("status") == "success":
                        otp = data.get("data", {}).get("otp")
                        if otp:
                            logger.info(f"THÔNG TIN: Lấy OTP thành công: {otp}")
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
    try:
        # Kiểm tra sự hiện diện của CAPTCHA bằng các yếu tố cụ thể
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "captcha-container")) or
            EC.presence_of_element_located((By.ID, "captchacharacters")) or
            EC.presence_of_element_located((By.ID, "cvfPhoneNumber")) or
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'a-box') and contains(., 'Enter the characters you see')]"))
        )
        logger.warning(f"CẢNH BÁO: Phát hiện CAPTCHA hoặc SDT cho {email}. Xem như lỗi và bỏ qua tài khoản.")
        return False
    except Exception:
        # Không tìm thấy CAPTCHA
        return True

# Hàm mô phỏng gõ giống con người
def human_type(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

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
        logger.info(f"THÔNG TIN: Đã lưu tài khoản {email} vào {file_path}")
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
        logger.warning(f"CẢNH BÁO: Đã ghi tài khoản lỗi {email} vào {file_path}")
    else:
        logger.info(f"THÔNG TIN: Tài khoản {email} đã có trong {file_path}, không ghi lại")

def click_element(driver, element, timeout=10):
    try:
        time.sleep(2)
        # Scroll element vào giữa màn hình
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        # Click bằng JS
        driver.execute_script("arguments[0].click();", element)
    except TimeoutException:
        logger.error("Timeout chờ element có thể click")
    except WebDriverException as e:
        logger.warning(f"Click bằng JS thất bại: {e}, thử dùng ActionChains...")
        try:
            from selenium.webdriver import ActionChains
            ActionChains(driver).move_to_element(element).click().perform()
        except Exception as ex:
            logger.error(f"Không thể chọn element bằng ActionChains: {ex}")
    except Exception as ex:
        logger.error(f"Lỗi không xác định khi click element: {ex}")

def get_2fa_code(secret_key):
    try:
        url = f"https://2fa.live/tok/{secret_key.replace(' ', '')}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"THÔNG TIN: Lấy được mã 2FA cho khóa: {secret_key} - {data.get('token')}")
            return data.get('token')
        else:
            logger.error(f"Không lấy được mã 2FA cho khóa: {secret_key}")
            return None
    except Exception as e:
        logger.error(f"Lỗi khi lấy mã 2FA: {repr(e)}")
        return None

def select_autocomplete(driver):
    try:
        # Chờ dropdown autocomplete xuất hiện
        time.sleep(random.uniform(1, 3))
        # Gửi phím DOWN và ENTER để chọn gợi ý đầu tiên
        driver.switch_to.active_element.send_keys(Keys.DOWN)
        time.sleep(random.uniform(0.1, 0.3))  # Chờ ngắn để mô phỏng hành vi người dùng
        driver.switch_to.active_element.send_keys(Keys.ENTER)
        logger.info("THÔNG TIN: Đã chọn gợi ý autocomplete cho địa chỉ")
    except Exception:
        # Nếu không có autocomplete, tiếp tục
        logger.info("THÔNG TIN: Không tìm thấy autocomplete, tiếp tục nhập địa chỉ")

# Hàm đăng ký Amazon chính
def register_amazon(username, sdt, address, proxy, password, shopgmail_api):
    gemlogin = GemLoginAPI()
    
    # Tạo Gmail mới
    email, orderid = shopgmail_api.create_gmail_account()
    if not email or not orderid:
        logger.error("CẢNH BÁO: Không thể tạo Gmail mới")
        return False
    
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
    try:
        def handle_reg_link(start_link):
            driver.get(start_link)
            wait = WebDriverWait(driver, 10)
            if "www.amazon.com/amazonprime" in start_link:
                form = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'form[action="/gp/prime/pipeline/membersignup"]'))
                )
                form.submit()

            # Chọn Tạo tài khoản
            create_account_button = wait.until(EC.presence_of_element_located((By.ID, "register_accordion_header")))
            click_element(driver, create_account_button)
            # Điền biểu mẫu đăng ký
            name_field = wait.until(EC.presence_of_element_located((By.ID, "ap_customer_name")))
            human_type(name_field, username)
            
            email_field = driver.find_element(By.ID, "ap_email")
            human_type(email_field, email)
            
            # password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            # password = "123456aA@Sang"
            password_field = driver.find_element(By.ID, "ap_password")
            human_type(password_field, password)
            click_element(driver, driver.find_element(By.ID, "continue"))
            
            # Kiểm tra CAPTCHA
            if not handle_captcha(driver, email):
                log_failed_account(email, "captcha.txt")
                return False
            return True
        
        start_links = read_file("reg_link.txt")
        check = False
        for start_link in start_links:
            if handle_reg_link(start_link):
                check = True
                break
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
        
        otp_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "cvf-input-code")))
        human_type(otp_field, otp)
        click_element(driver, driver.find_element(By.CSS_SELECTOR, "input[aria-label='Verify OTP Button']"))
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        
        # Điều hướng đến thiết lập 2FA
        driver.get(getattr(config, "2fa_amazon_link", "https://www.amazon.com/ax/account/manage?openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fyour-account%3Fref_%3Dya_cnep&openid.assoc_handle=anywhere_v2_us&shouldShowPasskeyLink=true&passkeyEligibilityArb=23254432-b9cb-4b93-98b6-ba9ed5e45a65&passkeyMetricsActionId=07975eeb-087d-42ab-971d-66c2807fe4f5"))
        
        # Kích hoạt 2FA
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "TWO_STEP_VERIFICATION_BUTTON"))).click()
        
        time.sleep(5)  # Wait for the page to load
        # get OTP again
        otp_2fa = shopgmail_api.get_otp(orderid)
        if not otp_2fa:
            logger.error(f"CẢNH BÁO: Không lý OTP 2FA cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        
        otp_field_2fa = driver.find_element(By.ID, "input-box-otp")
        human_type(otp_field_2fa, otp_2fa)
        formConfirm =  WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "verification-code-form")))
        formConfirm.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False
        
        # Id cvf-submit-otp-button
        click_element(driver, driver.find_element(By.ID, "sia-otp-accordion-totp-header"))
        # get sia-auth-app-formatted-secret
        backup_code = driver.find_element(By.ID, "sia-auth-app-formatted-secret").text
        
        # get 2fa OTP code from secret
        otp_2fa = get_2fa_code(backup_code)
        if not otp_2fa:
            logger.error(f"CẢNH BÁO: Không lấy được OTP 2FA cho {email}")
            log_failed_account(email, "captcha.txt")
            return False
        
        otp_field_2fa = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ch-auth-app-code-input")))
        human_type(otp_field_2fa, otp_2fa)
        formConfirm =  WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "sia-add-auth-app-form")))
        formConfirm.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False

        # Confirm button enable-mfa-form-submit
        enable_chechbox = driver.find_element(By.NAME, "trustThisDevice")
        click_element(driver, enable_chechbox)
        enable_2fa_form = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "enable-mfa-form")))
        enable_2fa_form.submit()
        
        # Kiểm tra CAPTCHA lần nữa
        if not handle_captcha(driver, email):
            log_failed_account(email, "captcha.txt")
            return False

        
        # Điều hướng đến sổ địa chỉ
        driver.get(getattr(config, "amazon_add_link","https://www.amazon.com/a/addresses/add?ref=ya_address_book_add_button"))
        
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
            logger.info(f"THÔNG TIN: Đăng ký thành công {email}")
            return True
        except Exception as e:
            logger.error(f"CẢNH BÁO: Thêm địa chỉ thất bại cho {email}: {str(e)}")
            log_failed_account(email, "chua_add.txt")
            return False
    except Exception as e:
        logger.error(f"CẢNH BÁO: Lỗi khi xử lý {email}: {str(e)}\n{traceback.format_exc()}")
        log_failed_account(email, "captcha.txt")
        return False
    finally:
        driver.quit()
        gemlogin.close_profile(profile_id)
        if not gemlogin.delete_profile(profile_id):
            logger.error(f"CẢNH BÁO: Không xóa được cấu hình {profile_id} cho {email}")


def register_and_cleanup(i, username, sdt, address, proxy, password, api):
    try:
        success = register_amazon(username, sdt, address, proxy, password, api)
        if success:
            remove_line("username.txt", i)
            remove_line("sdt.txt", i)
            remove_line("add.txt", i)
            remove_line("password.txt", i)
    except Exception as e:
        logger.error(f"Lỗi xử lý tài khoản {i}: {e}")


# Hàm chính
def main():
    # Nhập API key và số lượng tài khoản
    logger.info("THÔNG TIN: Đang kiểm tra apikey api.shopgmail9999.com")
    apikey = read_file("apikey.txt")
    if not apikey:
        logger.error("CẢNH BÁO: Không tìm thấy apikey. Vui lý nhập apikey.txt")
        return
    logger.info(f"API key: {apikey}")
    num_accounts = int(input("Nhập số tài khoản cần tạo: "))
    
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
    logger.info(f"THÔNG TIN: Sẽ xử lý {min_length} tài khoản")
    
    # Xử lý tài khoản đồng thời
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        for i in range(min_length):
            proxie = proxies[min_length % len(proxies)].strip()
            futures.append(executor.submit(register_and_cleanup, i, usernames[i], sdts[i], addresses[i], proxie, passwords[i], shopgmail_api))
            time.sleep(2)

        for future in futures:
            future.result()

if __name__ == "__main__":
    main()