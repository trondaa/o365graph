from flask import Flask, request, Response
import os
import sys
import logging
from sesamutils import VariablesConfig, sesam_logger

from graph import Graph
from utils import stream_json, determine_url_parts

app = Flask(__name__)

# Environment variables
required_env_vars = ["client_id", "client_secret", "grant_type", "resource", "entities_path", "next_page", "token_url"]
optional_env_vars = ["log_level", "base_url", "sleep", "sharepoint_url"]

logger = sesam_logger("o365graph")

config = VariablesConfig(required_env_vars, optional_env_vars=optional_env_vars)
if not config.validate():
    sys.exit(1)


data_access_layer = Graph(config)


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
@app.route("/list/<path:path>", methods=["GET", "POST"])
def list(path):
    if request.method == "GET":
        path = path
        entities = data_access_layer.get_list(path, args=request.args)

    if request.method == "POST":
        entities = request.get_json()





    return Response(
        stream_json(entities),
        mimetype='application/json'
    )



@app.route("/file/<path:path>", methods=["GET", "POST"])
def file(path):

    sharepoint_url = getattr(config, "sharepoint_url", None)
    if not sharepoint_url:
        return "Missing environment variable 'sharepoint_url' to use this url path", 500

    try:
        site, path, file_name, document_lib = determine_url_parts(sharepoint_url, path)
    except Exception as e:
        return Response(status=400, response=e)

    if request.method == "GET":
        if file_name:
            logger.info(f"Retrieving file from path '{path}'")
            file_resp = data_access_layer.get_file(path, site, document_lib)
            if file_resp:
                return file_resp
            Response(status=404, response="File not found")
        else:
            logger.info(f"Retrieving metadata for files on path '{path}'")
            path_children = data_access_layer.get_drive_path_nested_children(path, site, document_lib)
            return Response(stream_json(path_children), mimetype="application/json")
            # return Response(status=404, response="Path not found.")

    if request.method == "POST":
        if request.files:
            failures = False
            for file in request.files:
                if request.files[file].filename == '':
                    continue
                file_resp = data_access_layer.add_file(request.files[file], path, site, document_lib)
                if not file_resp.ok:
                    failures = True
                    logger.error(f"Failed to send file. Error: {file_resp.content}")
            if not failures:
                return Response(status=200)
        else:
            file_content = request.get_data()
            file_resp = data_access_layer.add_file(file_content, path, site, document_lib)
            if file_resp.ok:
                return Response(status=200)
        return Response(status=500, response="Failed to upload file to sharepoint. See ms logs for details.")


@app.route("/metadata/<path:path>", methods=["POST"])
def metadata(path):

    sharepoint_url = getattr(config, "sharepoint_url", None)
    if not sharepoint_url:
        return "Missing environment variable 'sharepoint_url' to use this url path", 500

    try:
        site, path, file_name, document_lib = determine_url_parts(sharepoint_url, path)
    except Exception as e:
        return Response(status=400, response=e)
    try:
        logger.debug(f"received raw body: {request.get_data()}")
        payload = request.get_json()
        if not payload:
            return Response(status=400, response=f"Received empty payload for path '{path}'")

        if isinstance(payload, list):
            payload = payload[0]

        logger.debug(f"received the following payload for path '{path}': \n{payload}")

        resp = data_access_layer.update_file_metadata(payload, path, site, document_lib)  # TODO: Need proper handling of invalid site/team
        if not resp.ok:
            return Response(status=resp.status_code, response=resp.content)
        return Response(status=200)
    except Exception as e:
        logger.error(e)
        return Response(status=500, response=e)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', threaded=True, port=5000)
