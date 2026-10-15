import copy

# 总店套餐模板
BASE_COMBO = {
    "combo_name": "经典双人餐",
    "price": 88.0,
    "dishes": ["东坡肉", "牛肉羹"]
}

# 1. 现场重现：浅拷贝引发的悲剧 ❌
hz_combo = copy.copy(BASE_COMBO)
hz_combo['price'] = 90
hz_combo['dishes'].append('cola')

print(f"hz_combo:{hz_combo}")
print(f"base combo:{BASE_COMBO}")
print("原因曝光：二者的 dishes 内存地址是否相同？", id(hz_combo["dishes"]) == id(BASE_COMBO["dishes"]))

# 2. TODO: 实验 2：企业级安全的深拷贝 (copy.deepcopy) ✅

CLEAN_BASE = {
        "combo_name": "经典双人餐",
        "price": 88.0,
        "dishes": ["东坡肉", "牛肉羹"]
}
nanjin_combo = copy.deepcopy(CLEAN_BASE)

nanjin_combo['price'] = 77.00
nanjin_combo['dishes'].append("grill duck")

print(nanjin_combo)
print(CLEAN_BASE)
print("原因曝光：二者的 dishes 内存地址是否相同？", id(nanjin_combo["dishes"]) == id(CLEAN_BASE["dishes"]))
