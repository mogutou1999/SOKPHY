# ✅ 正确：放到类里
class PaymentService:
    def __init__(self, api_key: str, sandbox: bool = False):
        self.api_key = api_key
        self.sandbox = sandbox

    def pay(self):
        print(f"用 {self.api_key} 支付，sandbox={self.sandbox}")
