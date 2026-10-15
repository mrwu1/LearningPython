
#全局- 获取命名空间，return a dict
# 所有对象都在内，所以，可以直接访问 【'a'】
scope = locals()
print(scope)
#{'__name__': '__main__', '__doc__': None, '__package__': None, '__loader__': <_frozen_importlib_external.SourceFileLoader object at 0x106a006b0>, '__spec__': None, '__builtins__': <module 'builtins' (built-in)>, '__file__': '/Users/anan/LearningPython/hello/src/video_study/07_locals.py', '__cached__': None, 'scope': {...}}

def fn():
    scope1 = locals()
    scope1['a'] = 12 #不推荐❌
    print(scope1)
    return 1

fn()