def handler(elem):
    name = elem["name"]
    fn, ln = name.split(" ")
    name = " ".join([ln, fn])
    elem["name_rev"] = name

    return elem