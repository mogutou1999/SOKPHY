from utils.alipay import generate_alipay_qr, verify_alipay_sign
from typing import Dict


class PaymentService:
    @staticmethod
    def create_payment(order_id: str, amount: float) -> str:
        """生成支付二维码"""
        return generate_alipay_qr(order_id, amount)

    @staticmethod
    def verify_callback(data: Dict) -> bool:
        """验证支付宝回调"""
        return verify_alipay_sign(data)
