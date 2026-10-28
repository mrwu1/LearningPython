"""
    Centralized Redis Lua Scripts Repository:
    Guarantees atomic execution inside Redis single-threaded runtime.
    """
# 分布式锁安全释放脚本 (Check-And-Delete: 校验 owner_token 匹配才允许删除)
LUA_RELEASE_LOCK_SCRIPT = """                                                                                        
   if redis.call("get", KEYS[1]) == ARGV[1] then                                                                        
       return redis.call("del", KEYS[1])                                                                                
   else                                                                                                                 
       return 0                                                                                                         
   end                                                                                                                  
"""

# 滑动窗口原子计数与裁剪脚本
LUA_SLIDING_WINDOW_SCRIPT = """                                                                                      
    local key = KEYS[1]                                                                                                  
    local now = tonumber(ARGV[1])                                                                                        
    local window = tonumber(ARGV[2])                                                                                     
    local max_limit = tonumber(ARGV[3])                                                                                  
    local member_id = ARGV[4]                                                                                            

    local clear_before = now - window                                                                                    
    redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)                                                            
    local current_count = redis.call('ZCARD', key)                                                                       

    if current_count < max_limit then                                                                                    
        redis.call('ZADD', key, now, member_id)                                                                          
        redis.call('EXPIRE', key, math.ceil(window) + 10)                                                                
        local remaining = max_limit - current_count - 1                                                                  
        return {1, remaining, 0}                                                                                         
    else                                                                                                                 
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')                                                     
        local retry_after = 1                                                                                            
        if #oldest >= 2 then                                                                                             
            local oldest_score = tonumber(oldest[2])                                                                     
            retry_after = math.max(1, math.ceil(oldest_score + window - now))                                            
        end                                                                                                              
        redis.call('EXPIRE', key, math.ceil(window) + 10)                                                                
        return {0, 0, retry_after}                                                                                       
    end                                                                                                                  
"""

# ---------------------------------------------------------------------------
# Lua 脚本（与原始版本一致，仅修正 release 逻辑：重入释放不续期）
# ---------------------------------------------------------------------------

# 可重入加锁：Hash 不存在则创建；存在且 field 匹配则 count+1
LUA_ACQUIRE = """
local key = KEYS[1]
local lease_ms = tonumber(ARGV[1])
local token = ARGV[2]

if redis.call('exists', key) == 0 then
    redis.call('hset', key, token, 1)
    redis.call('pexpire', key, lease_ms)
    return 1
end

if redis.call('hexists', key, token) == 1 then
    redis.call('hincrby', key, token, 1)
    redis.call('pexpire', key, lease_ms)
    return 1
end

return 0
"""

# 可重入释放：count-1；count==0 时 DEL 并 publish 通知
# 关键修复：counter > 0 时【不续期】，避免外层已死时内层 release 给锁续命
LUA_RELEASE = """
local key = KEYS[1]
local channel = KEYS[2]
local token = ARGV[1]

if redis.call('hexists', key, token) == 0 then
    return -1
end

local counter = redis.call('hincrby', key, token, -1)
if counter > 0 then
    return 0
end

redis.call('del', key)
redis.call('publish', channel, 'unlocked')
return 1
"""

# 看门狗续期：field 匹配才 PEXPIRE
LUA_RENEW = """
local key = KEYS[1]
local lease_ms = tonumber(ARGV[1])
local token = ARGV[2]

if redis.call('hexists', key, token) == 1 then
    redis.call('pexpire', key, lease_ms)
    return 1
end
return 0
"""