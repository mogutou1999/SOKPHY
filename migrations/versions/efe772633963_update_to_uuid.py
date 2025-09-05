
"""update foreign keys to uuid columns

Revision ID: your_new_revision_id
Revises: efe772633963
Create Date: 2025-09-04 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'efe772633963'  # 这里改成你的新迁移id，比如：'a1b2c3d4e5f6'
down_revision = '980d83ba6ce9'
branch_labels = None
depends_on = None


def upgrade():
    # 更新外键 UUID 关联字段
    op.execute("""
        UPDATE cart_items c
        SET new_user_id = u.new_id
        FROM users u
        WHERE c.user_id = u.id
    """)
    op.execute("""
        UPDATE cart_items c
        SET new_product_id = p.new_id
        FROM products p
        WHERE c.product_id = p.id
    """)
    op.execute("""
        UPDATE orders o
        SET new_user_id = u.new_id
        FROM users u
        WHERE o.user_id = u.id
    """)
    op.execute("""
        UPDATE order_items oi
        SET new_order_id = o.new_id
        FROM orders o
        WHERE oi.order_id = o.id
    """)
    op.execute("""
        UPDATE order_items oi
        SET new_product_id = p.new_id
        FROM products p
        WHERE oi.product_id = p.id
    """)
    op.add_column("products", sa.Column("price", sa.Float(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("stock", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("discount_price", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("is_discount_active", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    # 反向操作略
    pass
