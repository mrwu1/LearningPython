
#TODO:
# t - text file read  - 字符
# b - 二进制文件 read   - 字节  ‼️

file_name = "report.xlsx"

with open(file_name,mode="rb") as f:
    new_name = "a.xlsx"

    with open(new_name,'wb') as new_f:
        chunk = 1024 *100 # split chunks
        while True:
            content = f.read(chunk)
            if not content:
                break
            new_f.write(content)