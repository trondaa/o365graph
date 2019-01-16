from flask import Flask, request, Response
import os
import requests
import logging
import json
import dotdictify
from time import sleep
from requests.exceptions import HTTPError


app = Flask(__name__)
logger = None
format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logger = logging.getLogger('o365graph-service')

# Log to stdout

stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter(format_string))
logger.addHandler(stdout_handler)
logger.setLevel(logging.DEBUG)



def set_group_id(entity):
    for k, v in entity.items():
        if k.split(":")[-1] == "id":
            groupid = v
            logger.info(groupid)
        else:
            pass
    return groupid

##getting token from oauth2
def get_token():
    logger.info("Creating header")
    headers= {}
    payload = {
        "client_id":os.environ.get('client_id'),
        "client_secret":os.environ.get('client_secret'),
        "grant_type": os.environ.get('grant_type'),
        "resource": os.environ.get('resource')
    }
    #logger.info(payload)
    resp = requests.post(url=os.environ.get('token_url'), data=payload, headers=headers).json()
    token = dotdictify.dotdictify(resp).access_token
    logger.info("Received access token from " + os.environ.get('token_url'))
    return token

class DataAccess:

#main get function, will probably run most via path:path

    def __get_all_paged_entities(self, path, args):
        logger.info("Fetching data from paged url: %s", path)
        url = os.environ.get("base_url") + path
        access_token = get_token()
        next_page = url
        page_counter = 1
        while next_page is not None:
            if os.environ.get('sleep') is not None:
                logger.info("sleeping for %s milliseconds", os.environ.get('sleep') )
                sleep(float(os.environ.get('sleep')))

            logger.info("Fetching data from url: %s", next_page)
            if "$skiptoken" not in next_page:
                req = requests.get(next_page, params=args, headers={"Authorization": "Bearer " + access_token})

            else:
                 req = requests.get(next_page, headers={"Authorization": "Bearer " + access_token})

            if req.status_code != 200:
                logger.error("Unexpected response status code: %d with response text %s" % (req.status_code, req.text))
                raise AssertionError ("Unexpected response status code: %d with response text %s"%(req.status_code, req.text))
            res = dotdictify.dotdictify(json.loads(req.text))
            for entity in res.get(os.environ.get("entities_path")):

                yield(entity)

            if res.get(os.environ.get('next_page')) is not None:
                page_counter+=1
                next_page = res.get(os.environ.get('next_page'))
            else:
                next_page = None
        logger.info('Returning entities from %i pages', page_counter)

    def __get_all_siteurls(self, posted_entities):
        logger.info('fetching site urls')
        access_token = get_token()
        final_list = []
        for entity in posted_entities:
            url = "https://graph.microsoft.com/v1.0/groups/" + set_group_id(entity) + "/sites/root"
            req = requests.get(url=url, headers={"Authorization": "Bearer " + access_token})
            if req.status_code != 200:
                logger.info('no url')
            else:
                res = dotdictify.dotdictify(json.loads(req.text))
                final_list.append(res.copy())

        try:
            for entity in final_list:

                yield(entity)
        except Exception:
            logger.info('some wierd error occured')

    def get_paged_entities(self,path, args):
        print("getting all paged")
        return self.__get_all_paged_entities(path, args)

    def get_siteurls(self,posted_entities):
        print("getting all siteurls")
        return self.__get_all_siteurls(posted_entities)

data_access_layer = DataAccess()


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


@app.route("/<path:path>", methods=["GET", "POST"])
def get(path):
    if request.method == "POST":
        path = request.get_json()

    if request.method == "GET":
        path = path

    entities = data_access_layer.get_paged_entities(path, args=request.args)

    return Response(
        stream_json(entities),
        mimetype='application/json'
    )

@app.route("/siteurl", methods=["POST"])
def getsite():
    posted_entities = request.get_json()
    entities = data_access_layer.get_siteurls(posted_entities)

    return Response(
        stream_json(entities),
        mimetype='application/json'
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', threaded=True, port=os.environ.get('port',5000))
