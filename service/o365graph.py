from flask import Flask, request, Response
import os
import sys
import requests
import logging
import json
from dotdictify import dotdictify
from time import sleep
from requests.exceptions import HTTPError


app = Flask(__name__)

# Environment variables
required_env_vars = ["client_id", "client_secret", "grant_type", "resource", "entities_path", "next_page"]
optional_env_vars = ["log_level", "base_url", "sleep", "port"]


class AppConfig(object):
    pass


config = AppConfig()

# load variables
missing_env_vars = list()
for env_var in required_env_vars:
    value = os.getenv(env_var)
    if not value:
        missing_env_vars.append(env_var)
    setattr(config, env_var, value)

for env_var in optional_env_vars:
    value = os.getenv(env_var)
    if not value:
        value = None
    setattr(config, env_var, value)

# Set up logging
format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logger = logging.getLogger('o365graph-service')
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter(format_string))
logger.addHandler(stdout_handler)

loglevel = getattr(config, "log_level", "INFO")
level = logging.getLevelName(loglevel.upper())
if not isinstance(level, int):
    logger.warning("Unsupported log level defined. Using default level 'INFO'")
    level = logging.INFO
logger.setLevel(level)


if len(missing_env_vars) != 0:
    logger.error(f"Missing the following required environment variable(s) {missing_env_vars}")
    sys.exit(1)

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
    payload = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "grant_type": config.grant_type,
        "resource": config.resource
    }
    resp = requests.post(url=config.token_url, data=payload)
    if not resp.ok:
        logger.error(f"Access token request failed. Error: {resp.content}")
        raise
    token = dotdictify(resp.json()).access_token
    logger.info("Received access token from " + config.token_url)
    return token

class DataAccess:

#main get function, will probably run most via path:path

    def __init__(self):
        self.session = None
        self.auth_header = None

    def get_token(self):
        payload = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "grant_type": os.environ.get('grant_type'),
            "resource": config.resource
        }
        resp = requests.post(url=config.token_url, data=payload)
        if not resp.ok:
            logger.error(f"Access token request failed. Error: {resp.content}")
            raise
        access_token = resp.json().get("access_token")
        self.auth_header = {"Authorization": "Bearer " + access_token}

    def request(self, method, url, **kwargs):
        if not self.session:
            self.session = requests.Session()
            self.get_token()

        req = requests.Request(method, url, headers=self.auth_header, **kwargs)

        resp = self.session.send(req)
        if resp.status_code == 401:
            self.get_token()
            resp = self.session.send(req)

        return resp

    def __get_all_paged_entities(self, path, args):
        logger.info("Fetching data from paged url: %s", path)
        url = config.base_url + path
        next_page = url
        page_counter = 1
        while next_page is not None:
            if config.sleep is not None:
                logger.info("sleeping for %s milliseconds", config.sleep)
                sleep(float(config.sleep))

            logger.info("Fetching data from url: %s", next_page)
            if "$skiptoken" not in next_page:
                req = self.request("GET", next_page, params=args)
            else:
                req = self.request("GET", next_page)

            if req.status_code != 200:
                logger.error("Unexpected response status code: %d with response text %s" % (req.status_code, req.text))
                raise AssertionError ("Unexpected response status code: %d with response text %s"%(req.status_code, req.text))
            res = dotdictify(json.loads(req.text))
            for entity in res.get(config.entities_path):

                yield(entity)

            if res.get(config.next_page) is not None:
                page_counter+=1
                next_page = res.get(config.next_page)
            else:
                next_page = None
        logger.info('Returning entities from %i pages', page_counter)

    def __get_all_siteurls(self, posted_entities):
        logger.info('fetching site urls')
        for entity in posted_entities:
            url = "https://graph.microsoft.com/v1.0/groups/" + set_group_id(entity) + "/sites/root"
            req = self.request("GET", url)
            if req.status_code != 200:
                logger.info('no url')
            else:
                res = dotdictify(json.loads(req.text))
                res['_id'] = set_group_id(entity)

                yield res

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
    app.run(debug=True, host='0.0.0.0', threaded=True, port=getattr(config, 'port', 5000))
