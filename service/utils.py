import json
import logging

logger = logging.getLogger(f"o365graph.{__name__}")


def set_group_id(entity):
    for k, v in entity.items():
        if k.split(":")[-1] == "id":
            groupid = v
            logger.info(groupid)
        else:
            pass
    return groupid


def stream_json(entities):
    first = True
    yield '['
    for i, row in enumerate(entities):
        if not first:
            yield ','
        else:
            first = False
        yield json.dumps(row)
    yield ']'


def determine_url_parts(sharepoint_url, path):
    """Determine the different parts of the relative url"""
    file_name = False
    document_lib = False
    url_parts = path.split("/")
    if len(url_parts) < 3:
        error_message = f"Invalid path specified. Path need to start with site|group|team/<name>/. Path specified was '{path}'"
        raise Exception(error_message)
    site = sharepoint_url + "/" + "/".join(url_parts[:2])
    if ":" in url_parts[2]:
        document_lib = url_parts[2].split(":")[1]
        path = "/".join(url_parts[3:])
    elif ":" in url_parts[3]:
        document_lib = url_parts[3].split(":")[1]
        path = "/".join(url_parts[4:])
    elif ":" in url_parts[4]:
        document_lib = url_parts[4].split(":")[1]
        path = "/".join(url_parts[5:])
    else:
        path = "/".join(url_parts[2:])
    possible_file_name = url_parts[len(url_parts)-1]
    if len(possible_file_name.split(".")) > 1:
        file_name = possible_file_name

    return site, path, file_name, document_lib


# def set_updated(entity, args):
#     since_path = args.get("since_path")
#
#     if since_path is not None:
#         b = Dotdictify(entity)
#         entity["_updated"] = b.get(since_path)

# def rename(entity):
#     for key, value in entity.items():
#         res = dict(entity[key.split(':')[1]]=entity.pop(key))
#     logger.info(res)
#     return entity['id']