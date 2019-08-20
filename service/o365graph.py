from flask import Flask, request, Response, abort, jsonify
import os
import sys
import requests
import logging
import json
from dotdictify import dotdictify
from time import sleep
from urllib.parse import urlparse


app = Flask(__name__)

# Environment variables
required_env_vars = ["client_id", "client_secret", "grant_type", "resource", "entities_path", "next_page", "token_url"]
optional_env_vars = ["log_level", "base_url", "sleep", "port", "sharepoint_url"]


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
    if value:
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


class Graph:

    FILE_SIZE_LIMIT = 4000000  # bytes

    def __init__(self):
        self.session = None
        self.auth_header = None
        self.graph_url = getattr(config, "base_url", None) or "https://graph.microsoft.com/v1.0/"

    def get_token(self):
        payload = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "grant_type": config.grant_type,
            "resource": config.resource
        }
        logger.info("Acquiring new access token")
        try:
            resp = requests.post(url=config.token_url, data=payload)
            if not resp.ok:
                logger.error(f"Access token request failed. Error: {resp.content}")
                raise
        except Exception as e:
            logger.error(f"Failed to talk to token service. Error: {e}")
            raise
        access_token = resp.json().get("access_token")
        self.auth_header = {"Authorization": "Bearer " + access_token}

    def request(self, method, url, **kwargs):
        if not self.session:
            self.session = requests.Session()
            self.get_token()

        if "headers" in kwargs:
            headers = {**kwargs["headers"], **self.auth_header}
            kwargs.pop("headers")
        else:
            headers = self.auth_header

        logger.debug(f"Using following headers: \n{headers}")
        req = requests.Request(method, url, headers=headers, **kwargs)

        resp = self.session.send(req.prepare())
        if resp.status_code == 401:
            logger.warning("Received status 401. Requesting new access token.")
            self.get_token()
            resp = self.session.send(req.prepare())

        return resp

    def __get_all_paged_entities(self, path, args):
        logger.info(f"Fetching data from paged url: {path}")
        url = self.graph_url + path
        next_page = url
        page_counter = 1
        while next_page is not None:
            if hasattr(config, "sleep"):
                logger.info(f"sleeping for {config.sleep} milliseconds")
                sleep(float(config.sleep))

            logger.info(f"Fetching data from url: {next_page}")
            if "$skiptoken" not in next_page:
                req = self.request("GET", next_page, params=args)
            else:
                req = self.request("GET", next_page)

            if not req.ok:
                error_text = f"Unexpected response status code: {req.status_code} with response text {req.text}"
                logger.error(error_text)
                raise AssertionError(error_text)
            res = dotdictify(req.json())
            for entity in res.get(config.entities_path):

                yield(entity)

            if res.get(config.next_page) is not None:
                page_counter += 1
                next_page = res.get(config.next_page)
            else:
                next_page = None
        logger.info(f"Returning entities from {page_counter} pages")

    def __get_all_siteurls(self, posted_entities):
        logger.info('fetching site urls')
        for entity in posted_entities:
            url = self.graph_url + "groups/" + set_group_id(entity) + "/sites/root"
            req = self.request("GET", url)
            if not req.ok:
                logger.info('no url')
            else:
                res = dotdictify(req.json())
                res['_id'] = set_group_id(entity)

                yield res

    def get_paged_entities(self, path, args):
        print("getting all paged")
        return self.__get_all_paged_entities(path, args)

    def get_siteurls(self, posted_entities):
        print("getting all siteurls")
        return self.__get_all_siteurls(posted_entities)

    def _get_sharepoint_site_id(self, site):
        """Find the sharepoint id for a given site or team based on site's relative url"""

        url = self.graph_url + "sites/" + site
        logger.debug(f"sharepoint site id url: '{url}'")
        resp = self.request("GET", url)
        if not resp.ok:
            logger.error(f"Unable to determine site id for site '{site}'. Error: {resp.text}")
            return None
        return resp.json().get("id")

    def _get_site_documents_drive_url(self, site):
        """Find the drive id for the sharepoint site/team documents directory"""

        site_id = self._get_sharepoint_site_id(site)
        if site_id:
            url = self.graph_url + "/sites/" + site_id + "/drive"
            logger.debug(f"site documents drive url: '{url}'")
            resp = self.request("GET", url)
            if not resp.ok:
                logger.error(f"Unable to determine documents drive id for site '{site}'. Error: {resp.text}")
                return None
            drive_id = resp.json().get("id")
            drive_url = url + "s/" + drive_id + "/root"
            return drive_url
        logger.error("Unable to determine documents drive id without a valid site_id")
        return None

    def _get_drive_path_children(self, path, site):
        """Get all the children for the given path"""

        drive_url = self._get_site_documents_drive_url(site)
        if drive_url:
            if path:
                children_url = drive_url + ":/" + path + ":/children?$expand=listItem($expand=fields)"
            else:
                children_url = drive_url + "/children?$expand=listItem($expand=fields)"

            resp = self.request("GET", children_url) # TODO: add support for paging (limit of 200 entities)
            if not resp.ok:
                logger.error(f"Failed to get children for path '{path}'. Error: {resp.content}")
                return resp
            return resp.json().get("value")
        return None

    def get_drive_path_nested_children(self, path, site):
        """Get all the children and their children for the given path"""
        try:
            top_children = self._get_drive_path_children(path, site)
            if not isinstance(top_children, list) and top_children.status_code == 404:
                error_message = f"404 - Path '{path}' not found"
                logger.info(error_message)
                raise Exception(error_message)
            if top_children and isinstance(top_children, list):
                for child in top_children:
                    if "folder" in child:
                        # this is a folder
                        new_path = f"{path}/{child['name']}"
                        children = self.get_drive_path_nested_children(new_path, site)
                        if children:
                            for child in children:
                                child["source_path"] = f"{new_path}"
                                child["_id"] = child.get("id")
                                yield child
                    else:
                        child["source_path"] = f"{path}"
                        child["_id"] = child.get("id")
                        yield child
        except Exception as e:
            yield {"error": str(e)}

    def _get_file_download_url(self, path, site):
        """Get the file download url for a given file path in given sharepoint site/team"""
        drive_url = self._get_site_documents_drive_url(site)
        if drive_url:
            url = drive_url + ":/" + path
            logger.debug(f"File details request url: '{url}'")
            resp = self.request("GET", url)
            if not resp.ok:
                logger.error(f"Failed to get download url for file '{path}' on '{site}'. Error: {resp.text}")
                return None
            return resp.json().get("@microsoft.graph.downloadUrl")
        logger.error("Unable to determine download url without valid drive url.")
        return None

    def _get_file_upload_url(self, path, site, session=None):
        """Get the file upload url for a given file path in the given sharepoint site/team"""
        drive_url = self._get_site_documents_drive_url(site)
        if session:
            return drive_url + ":/" + path + ":/createUploadSession"
        return drive_url + path + ":/content"

    def get_file(self, path, site):
        """Get file from sharepoint file directory"""

        download_url = data_access_layer._get_file_download_url(path, site)
        logger.debug(f"File download url: '{download_url}'")
        resp = requests.get(download_url)  # No auth required for this url
        if not resp.ok:
            logger.error(f"Failed to retrieve file from path '{path}'. Error: {resp.text}")
            return None
        return resp.content

    def add_file(self, content, path, site):
        """Add file to filepath"""

        # check payload size to determine upload stategy
        try:
            payload_size = len(content.read())
            content.seek(0)
            logger.debug(f"File size: {payload_size}")
            if payload_size > self.FILE_SIZE_LIMIT:
                # need to use upload session
                headers = {
                    "Content-Range": f"bytes 0-{payload_size-1}/{payload_size}",
                    "Content-Length": str(payload_size)
                }

                session_url = self._get_file_upload_url(path, site, session=True)

                session_resp = self.request("POST", session_url)
                if not session_resp.ok:
                    logger.error(f"Failed to create upload session for path '{path}'.")
                    return session_resp
                logger.debug(f"Upload session response: {session_resp.content}")

                upload_url = session_resp.json().get("uploadUrl")
                if not upload_url:
                    logger.error("UploadUrl missing from upload session response.")
                    return session_resp

                resp = self.request("PUT", upload_url, data=content, headers=headers)
                logger.debug(f"Upload session file PUT operation response: {resp.content}")
                if not resp.ok:
                    logger.error(f"Failed to send file with path '{path}' to sharepoint through upload session. Response: {resp.text}")
                return resp
            else:
                # Simple put operation upload
                upload_url = self._get_file_upload_url(path, site)
                resp = self.request("PUT", upload_url, data=content)
                if not resp.ok:
                    logger.error(f"Failed to send file with path '{path}' to sharepoint. Response: {resp.text}")
                return resp
        except Exception as e:
            logger.error(e)

    def update_file(self, content, path, site):

        # TODO: Add support for updating existing files

        pass


data_access_layer = Graph()


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


@app.route("/entities/<path:path>", methods=["GET", "POST"])
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


@app.route("/file/<path:path>", methods=["GET", "POST"])
def file(path):

    sharepoint_url = getattr(config, "sharepoint_url", None)
    if not sharepoint_url:
        return "Missing environment variable 'sharepoint_url' to use this url path", 500

    sharepoint_url = urlparse(sharepoint_url).netloc

    url_parts = path.split("/")
    if len(url_parts) < 3:
        error_message = f"Invalid path specified. Path need to start with site|group|team/<name>/. Path specified was '{path}'"
        logger.error(error_message)
        return Response(status=400, response=error_message)

    site = sharepoint_url + ":/" + "/".join(url_parts[:2])
    path = "/".join(url_parts[2:])
    file_name = url_parts[len(url_parts)-1]
    is_file = False
    if len(file_name.split(".")) > 1:
        is_file = True

    if request.method == "GET":
        if is_file:
            logger.info(f"Retrieving file from path '{path}'")
            file_resp = data_access_layer.get_file(path, site)
            if file_resp:
                return file_resp
            Response(status=404, response="File not found")
        else:
            logger.info(f"Retrieving metadata for files on path '{path}'")
            path_children = data_access_layer.get_drive_path_nested_children(path, site)
            return Response(stream_json(path_children), mimetype="application/json")
            # return Response(status=404, response="Path not found.")

    if request.method == "POST":
        if request.files:
            failures = False
            for file in request.files:
                if request.files[file].filename == '':
                    continue
                file_resp = data_access_layer.add_file(request.files[file], path, site)
                if not file_resp.ok:
                    failures = True
                    logger.error(f"Failed to send file. Error: {file_resp.content}")
            if not failures:
                return Response(status=200)
        else:
            file_content = request.get_data()
            file_resp = data_access_layer.add_file(file_content, path, site)
            if file_resp.ok:
                return Response(status=200)
        return Response(status=500, response="Failed to upload file to sharepoint. See ms logs for details.")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', threaded=True, port=getattr(config, 'port', 5000))
