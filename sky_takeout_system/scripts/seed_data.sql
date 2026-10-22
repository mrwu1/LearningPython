-- ==============================================================================
-- Sky Takeout Enterprise Database Seed Script
-- Target Database: sky_takeout_agent (MySQL 8.0)
-- Description: Idempotent seed data for Dishes and Live Orders
-- ==============================================================================

-- 1. Seed Dishes (Dishes available in kitchen catalog)
INSERT INTO dishes (name, price, stock, prep_time_minutes, status, created_at, updated_at)
VALUES 
    ('挪威轻食三文鱼沙拉', 48.00, 15, 12, 1, NOW(), NOW()),
    ('经典西冷牛排套餐', 88.00, 8, 25, 1, NOW(), NOW()),
    ('低卡照烧鸡胸肉便当', 32.00, 20, 15, 1, NOW(), NOW()),
    ('意式黑椒牛肉意面', 42.00, 12, 18, 1, NOW(), NOW()),
    ('缤纷牛油果时蔬能量碗', 38.00, 5, 10, 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE 
    price = VALUES(price),
    stock = VALUES(stock),
    updated_at = NOW();

-- 2. Seed Live Orders for Testing
INSERT INTO orders (order_number, user_id, total_amount, status, courier_name, courier_distance_meters, delivery_eta_minutes, created_at, updated_at)
VALUES 
    ('ORD-TAKEOUT-9901', 'USER_1001', 48.00, 'COMPLETED', '张师傅', 0, 0, NOW(), NOW()),
    ('ORD-TAKEOUT-9902', 'USER_1002', 88.00, 'DELIVERING', '李师傅', 650, 8, NOW(), NOW()),
    ('ORD-TAKEOUT-9903', 'USER_1003', 120.00, 'COMPLETED', '王师傅', 0, 0, NOW(), NOW())
ON DUPLICATE KEY UPDATE 
    status = VALUES(status),
    courier_distance_meters = VALUES(courier_distance_meters),
    delivery_eta_minutes = VALUES(delivery_eta_minutes),
    updated_at = NOW();
