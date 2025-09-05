# utils/admin_session.py

class AdminProductSession:
    sessions = {}

    @classmethod
    def set_price(cls, user_id, price):
        cls.sessions.setdefault(user_id, {})["price"] = price

    @classmethod
    def set_stock(cls, user_id, stock):
        cls.sessions.setdefault(user_id, {})["stock"] = stock

    @classmethod
    def set_description(cls, user_id, description):
        cls.sessions.setdefault(user_id, {})["description"] = description

    @classmethod
    def set_name(cls, user_id, name):
        cls.sessions.setdefault(user_id, {})["name"] = name

    @classmethod
    def get(cls, user_id):
        return cls.sessions.get(user_id)

    @classmethod
    def clear(cls, user_id):
        cls.sessions.pop(user_id, None)
