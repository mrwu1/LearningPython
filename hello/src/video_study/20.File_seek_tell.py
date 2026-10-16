import os
from pprint import pprint

file_name="demo.txt"
with open(file_name,"r",encoding="utf-8") as f:

    # todo: tell() - 当前读取的位置
    f.readline()
    print(f.tell())

    # todo: seek() - 修改当前读取的位置


pprint(os.listdir())
#todo: rmdir,remove