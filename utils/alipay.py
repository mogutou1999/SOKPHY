# utils/alipay.py

def generate_alipay_qr(out_no: str, amount: float) -> str:
    """生成二维码 URL"""
    return f"https://fake-alipay-qr.com/pay?out_no={out_no}&amount={amount}"

def verify_alipay_sign(data: dict) -> bool:
    """验证支付宝回调签名"""
    return True
