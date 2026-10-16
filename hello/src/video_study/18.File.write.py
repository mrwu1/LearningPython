
#todo: write

file_name = "demo.txt"
# r - read
with open(file_name,encoding="utf-8",mode='a') as f:

    # todo: w - not exist, create; exist, clear then write
    f.write("today is a good day!")

    f.write("today\n")

    # todo: a - add

    # todo: r+, w+

    # todo: x

    f.write("today is a good day!")