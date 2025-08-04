import pyotp
import logging

logger = logging.getLogger(__name__)

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

# Example usage
if __name__ == "__main__":
    secret = "5C5I BCWG UGYL YAUV 5SJP M7QM Z5XU EF22 BRXC KZVD 5OJG KKQR UNTQ"
    code = get_2fa_code(secret)
    if code:
        print(f"Generated 2FA code: {code}")
    else:
        print("Failed to generate 2FA code.")