import os
import sys
from pprint import pprint

# 引入的模块
print(sys.argv)

# 引入的所有model
pprint(sys.modules)

# model
pprint(sys.path)

print(sys.platform) # darwin

# sys.exit()
print(sys.version)

print("-----------------------------")
#os model
pprint(os)
print(os.name)