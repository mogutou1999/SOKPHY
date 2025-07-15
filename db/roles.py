# roles.py


import enum


class Role(enum.Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SUPERADMIN = "superadmin"
