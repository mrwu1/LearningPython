
file_name = "demo.txt"

#todo: 默认为 None
open_file = open(file_name,encoding="utf-8")

# TODO: <_io.TextIOWrapper name='demo.txt' mode='r' encoding='UTF-8'>
print(open_file)


#TODO: read - with: close automatically
# with open_file as f:
#     print(f.read())


#TODO: close
# open_file.close()


# todo: read # 字符
# todo: utf-8, 二进制
try:
    with open(file_name,encoding="utf-8") as f:
            line = f.read(3)
            print(line)
except FileExistsError as e:
    print(e)

#todo: huge file
try:
    with open(file_name,encoding="utf-8") as f:
        chunk = 2 # split chunks
        while True:
            content = f.read(chunk)
            if not content:
                break
            print(content,end='')
except FileNotFoundError as e:
    print(e)