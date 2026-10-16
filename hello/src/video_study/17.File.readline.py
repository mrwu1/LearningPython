from pprint import pprint

file_name = "demo.txt"
with open(file_name,"r",encoding="utf-8") as f:
    #todo: line
    # print(f.readline())

    #todo: all
    p = f.readlines()
    pprint(p)