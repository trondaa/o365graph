
import logging
import requests
from time import sleep
from sesamutils import Dotdictify
from urllib.parse import urlparse, quote

from utils import set_group_id

logger = logging.getLogger(f"o365graph.{__name__}")

class Graph:

    FILE_SIZE_LIMIT = 4000000  # bytes

    def __init__(self, config):
        self.session = None
        self.auth_header = None
        self.graph_url = getattr(config, "base_url", None) or "https://graph.microsoft.com/v1.0/"
        self.config = config

    def get_token(self):
        payload = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": self.config.grant_type,
            "resource": self.config.resource
        }
        logger.info("Acquiring new access token")
        try:
            resp = requests.post(url=self.config.token_url, data=payload)
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

        if "json" in kwargs:
            headers = {**headers, "Content-Type": "application/json"}

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
            if hasattr(self.config, "sleep"):
                logger.info(f"sleeping for {self.config.sleep} milliseconds")
                sleep(float(self.config.sleep))

            logger.info(f"Fetching data from url: {next_page}")
            if "$skiptoken" not in next_page:
                req = self.request("GET", next_page, params=args)
            else:
                req = self.request("GET", next_page)

            if not req.ok:
                error_text = f"Unexpected response status code: {req.status_code} with response text {req.text}"
                logger.error(error_text)
                raise AssertionError(error_text)
            res = Dotdictify(req.json())
            for entity in res.get(self.config.entities_path):

                yield(entity)

            if res.get(self.config.next_page) is not None:
                page_counter += 1
                next_page = res.get(self.config.next_page)
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
                res = Dotdictify(req.json())
                res['_id'] = set_group_id(entity)

                yield res

    def __get_list(self, path, args):
        logger.info('fetching list urls')

        url = self.graph_url + "sites/" + path + "items?$expand=fields"
        req = self.request("GET", url)
        if not req.ok:
            logger.info('no url')
        else:
            res = Dotdictify(req.json())

            yield res

    def get_paged_entities(self, path, args):
        print("getting all paged")
        return self.__get_all_paged_entities(path, args)

    def get_siteurls(self, posted_entities):
        print("getting all siteurls")
        return self.__get_all_siteurls(posted_entities)

    def get_list(self, path, args):
        print("getting list")
        return self.__get_list(path, args)

    def _get_sharepoint_site_id(self, site):
        """Find the sharepoint id for a given site or team based on site's relative url"""

        site_parts = urlparse(site)

        url = self.graph_url + "sites/" + site_parts.netloc + ":" + site_parts.path
        logger.debug(f"sharepoint site id url: '{url}'")
        resp = self.request("GET", url)
        if not resp.ok:
            logger.error(f"Unable to determine site id for site '{site}'. Error: {resp.text}")
            return None
        return resp.json().get("id")

    def _get_site_documents_drive_url(self, site, document_lib=None):
        """Find the drive id for the sharepoint site/team documents directory"""

        site_id = self._get_sharepoint_site_id(site)
        if site_id:
            if document_lib:
                url = self.graph_url + "/sites/" + site_id + "/drives"
            else:
                url = self.graph_url + "/sites/" + site_id + "/drive"
            logger.debug(f"site documents drive url: '{url}'")
            resp = self.request("GET", url)
            if not resp.ok:
                logger.error(f"Unable to determine documents drive id for site '{site}'. Error: {resp.text}")
                return None
            response_payload = resp.json()
            if document_lib and len(response_payload.get("value")) > 0:
                for lib in response_payload.get("value"):
                    if lib["name"] == document_lib:
                        drive_id = lib["id"]
                if "drive_id" not in locals():
                    logger.error(f"Unable to find id for document library '{document_lib}'")
                    return None
            else:
                drive_id = response_payload.get("id")
                url = url + "s"
            drive_url = url + "/" + drive_id + "/root"
            return drive_url
        logger.error("Unable to determine documents drive id without a valid site_id")
        return None

    def _get_drive_path_children(self, path, site, document_lib=None):
        """Get all the children for the given path"""

        drive_url = self._get_site_documents_drive_url(site, document_lib)
        if drive_url:
            if path:
                children_url = drive_url + ":/" + quote(path) + ":/children?$expand=listItem($expand=fields)"
            else:
                children_url = drive_url + "/children?$expand=listItem($expand=fields)"

            next_page = True
            url = children_url
            while next_page:
                resp = self.request("GET", url)
                resp_payload = resp.json()
                if "@odata.nextLink" in resp_payload:
                    url = resp_payload["@odata.nextLink"]
                else:
                    next_page = False
                yield resp_payload.get("value")
        return None

    def get_drive_path_nested_children(self, path, site, document_lib=None):
        """Get all the children and their children for the given path"""
        try:
            top_children_generator = self._get_drive_path_children(path, site, document_lib)
            if top_children_generator:
                for top_children in top_children_generator:
                    for child in top_children:
                        if "folder" in child:
                            # this is a folder
                            new_path = f"{path}/{child['name']}"
                            children = self.get_drive_path_nested_children(new_path, site, document_lib)
                            if children:
                                for child in children:
                                    child["source_path"] = f"{new_path}"  # Todo: Something's wrong here. It ends up with wrong path on some occasions
                                    child["_id"] = child.get("id")
                                    yield child
                        else:
                            child["source_path"] = f"{path}"
                            child["_id"] = child.get("id")
                            yield child
        except Exception as e:
            logger.error(f"Failure during traversal of path. Error: {e}")
            yield {"error": str(e)}

    def _get_file_download_url(self, path, site, document_lib=None):
        """Get the file download url for a given file path in given sharepoint site/team"""
        drive_url = self._get_site_documents_drive_url(site, document_lib)
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

    def _get_file_upload_url(self, path, site, document_lib=None, session=None):
        """Get the file upload url for a given file path in the given sharepoint site/team"""
        file_url = self._get_file_url(path, site, document_lib)
        if session:
            return file_url + ":/createUploadSession"
        return file_url + ":/content"

    def _get_file_url(self, path, site, document_lib=None):
        """Get base url for file path"""
        return self._get_site_documents_drive_url(site, document_lib) + ":/" + quote(path)

    def get_file(self, path, site, document_lib=None):
        """Get file from sharepoint file directory"""

        download_url = self._get_file_download_url(path, site, document_lib)
        logger.debug(f"File download url: '{download_url}'")
        resp = requests.get(download_url)  # No auth required for this url
        if not resp.ok:
            logger.error(f"Failed to retrieve file from path '{path}'. Error: {resp.text}")
            return None
        return resp.content

    def add_file(self, content, path, site, document_lib=None):
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

                session_url = self._get_file_upload_url(path, site, document_lib, session=True)

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
                upload_url = self._get_file_upload_url(path, site, document_lib)
                resp = self.request("PUT", upload_url, data=content)
                if not resp.ok:
                    logger.error(f"Failed to send file with path '{path}' to sharepoint. Response: {resp.text}")
                return resp
        except Exception as e:
            logger.error(e)

    def update_file(self, content, path, site):

        # TODO: Add support for updating existing files

        pass

    def update_file_metadata(self, payload, file_path, site, document_lib=None):
        """Update column values for the given file"""
        file_url = self._get_file_url(file_path, site, document_lib) + ":/listItem/fields"
        logger.debug(f"Updating metadata for file path '{file_path}' with url '{file_url}'")
        return self.request("PATCH", file_url, json=payload)
