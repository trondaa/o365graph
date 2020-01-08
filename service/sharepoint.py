
import sharepy
import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(f"o365graph.{__name__}")


class Sharepoint(object):

    def __init__(self, site_url, username, password):

        self.session = sharepy.connect(site_url,
                                       username,
                                       password)
        self.site_url = site_url

    def _get_digest(self):

        digest_url = self.site_url + "/_api/contextinfo"

        resp = self.session.post(digest_url)
        if resp.ok:
            try:
                content = resp.json()
                digest_value = content['d']['GetContextWebInformation']['FormDigestValue']
                return digest_value
            except KeyError:
                logger.error("Unable to retrieve digest value.")

        return None

    def _determine_payload_metadata_type(self, url):

        resp = self.session.get(url)

        if resp.ok:
            try:
                return resp.json()["d"]["__metadata"]["type"]
            except Exception as e:
                print(f"Unable to determine payload metadata type. Error: {e}")
        else:
            logger.error(f"Error received while trying to determine metadata type: {resp.text}")
        return None

    def update_metadata(self, payload, path, document_lib=False):

        digest = self._get_digest()
        if not digest:
            logger.error("Cannot complete request without valid digest value.")
            return False

        site_url_parts = urlparse(self.site_url)

        if not document_lib:
            document_lib = "Shared Documents"

        update_url = f"{self.site_url}/_api/Web/GetFileByServerRelativeUrl('{site_url_parts.path}/{document_lib}/{path}')/ListItemAllFields"
        logger.debug(f"Using following url to update metadata: '{update_url}'")

        metadata = self._determine_payload_metadata_type(update_url)

        if not metadata:
            logger.error(f"Unable to determine metadata type for url '{update_url}'")
            return False

        target_payload = {**payload, "__metadata": {"type": metadata}}

        headers = {
            "Content-Length": str(len(json.dumps(target_payload))),
            "Accept": "application/json; odata=verbose",
            "Content-Type": "application/json; odata=verbose",
            "X-RequestDigest": digest,
            "IF-MATCH": "*",
            "X-HTTP-Method": "MERGE"
        }

        resp = self.session.post(update_url, headers=headers, json=target_payload)
        if resp.ok:
            logger.debug(f"Successfully updated metadata for path '{path}'")
            return True
        logger.error(f"Failed to update metadata for path '{path}'. Error: {resp.text}")
        return False

