-- ========================================
-- 初始化数据库 & 示例数据 (PostgreSQL)
-- ========================================

-- -----------------------
-- 用户表
-- -----------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(64),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------
-- 商品表
-- -----------------------
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    price NUMERIC(10,2) NOT NULL,
    stock INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------
-- 购物车表
-- -----------------------
CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,
    product_name VARCHAR(128),
    unit_price NUMERIC(10,2),
    quantity INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------
-- 订单表
-- -----------------------
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    total_amount NUMERIC(10,2),
    status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------
-- 订单明细
-- -----------------------
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id),
    quantity INT DEFAULT 1,
    unit_price NUMERIC(10,2)
);

-- -----------------------
-- 示例管理员
-- -----------------------
INSERT INTO users (telegram_id, username, is_admin)
VALUES
(123456789, 'admin', TRUE)
ON CONFLICT (telegram_id) DO NOTHING;

-- -----------------------
-- 示例商品
-- -----------------------
INSERT INTO products (name, description, price, stock, is_active)
VALUES
('测试商品1', '这是第一个测试商品', 9.90, 10, TRUE),
('测试商品2', '这是第二个测试商品', 19.90, 5, TRUE),
('测试商品3', '这是第三个测试商品', 29.90, 20, TRUE)
ON CONFLICT (id) DO NOTHING;