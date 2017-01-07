import requests
import json
import sys
from requests.exceptions import HTTPError, ConnectTimeout

knownWindowsLayers = {
    "sha256:3889bb8d808bbae6fa5a33e07093e65c31371bcf9e4c38c21be6b9af52ad1548": "microsoft/windowsservercore:10.0.14393.576 update",
    "sha256:04ee5d718c7adc0144556d740900f778129e41be806c95191710d1d92051a7b3": "microsoft/windowsservercore:10.0.14393.576 base",
    "sha256:d33fff6043a134da85e10360f9932543f1dfc0c3a22e1edd062aa9b088a86c5b": "microsoft/windowsservercore:10.0.14393.447 update",
    "sha256:de5064718b3f2749727c8b5ffddf2da7698189277afe0df6fc0a57ad573bca0f": "microsoft/windowsservercore:10.0.14393.321 update",
    "sha256:9c7f9c7d9bc2915388ecc5d08e89a7583658285469d7325281f95d8ee279cc60": "microsoft/windowsservercore:10.0.14393.206 base",

    "sha256:10bf725c5388a1909f7184467b5ec75dbad3ece68508aa5fa4074baa0b20cc6f": "microsoft/nanoserver:10.0.14393.576 update",
    "sha256:bce2fbc256ea437a87dadac2f69aabd25bed4f56255549090056c1131fad0277": "microsoft/nanoserver:10.0.14393.576 base",
    "sha256:482ab31872a23b32cbdeca13edb7a0b97290714c0b5edcce96fbb3e34221ea91": "microsoft/nanoserver:10.0.14393.447 update",
    "sha256:94b4ce7ac4c7c7d4ed75ac2bd9359a87204ad2d5a909759d8e77953874d8e7c2": "microsoft/nanoserver:10.0.14393.321 update",
    "sha256:5496abde368a3dd39999745bf998c877ddc6a390a943bc3fd99ffaabf728ed88": "microsoft/nanoserver:10.0.14393.206 base",
}

class DockerImageInspector(object):

    def __init__(self, registry_hostname, repository_name, tag="latest"):
        self.base_url = "https://%s" % registry_hostname
        self.repository_name = repository_name
        self.token = None
        self.tag = tag
        self.create_date = None
        self.layers = []
        self.tags = []
        self.manifest = None
        self.get_tags()
        self.get_manifest()

    def get_tags(self):
        url = "{base_url}/v2/{name}/tags/list".format(
                base_url=self.base_url,
                name=self.repository_name)
        headers = {}
        if self.token is not None:
            headers["Authorization"] = "Bearer %s" % self.token
        r = requests.get(url, headers=headers, timeout=(3.05,10))
        r.raise_for_status()
        self.tags = r.json()["tags"]

    def get_manifest(self):
        url = "{base_url}/v2/{name}/manifests/{reference}".format(
                base_url=self.base_url,
                name=self.repository_name,
                reference=self.tag)
        headers = {
            "Accept": "application/vnd.docker.distribution.manifest.v2+json"
        }
        if self.token is not None:
            headers["Authorization"] = "Bearer %s" % self.token
        r = requests.get(url, headers=headers, timeout=(3.05,10))
        r.raise_for_status()
        self.manifest = r.json()
        print(self.manifest)
        for l in self.manifest["layers"]:
            self.layers.append(l)
        self.manifest_content_type = r.headers["content-type"]


class DockerHubImageInspector(DockerImageInspector):

    def __init__(self, repository_name, tag="latest"):
        self.base_url = "https://registry.hub.docker.com"
        self.repository_name = repository_name
        self.__get_token()
        self.tag = tag
        self.layers = []
        self.tags = []
        self.manifest = None
        self.get_tags()
        self.get_manifest()

    def __get_token(self):
        url = "https://auth.docker.io/token"
        params = {
            "service": "registry.docker.io",
            "scope": "repository:{name}:pull".format(
                name=self.repository_name)
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        self.token = r.json()["token"]



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Inspect an image from DockerHub')
    parser.add_argument('image', metavar='IMAGE',
                        help='The image to look for, e.g. "library/redis"')

    args = parser.parse_args()
    if ":" in args.image:
        (image, tag) = args.image.split(":")
    else:
        image = args.image
        tag = "latest"

    image_parts = image.split("/")
    registry = None
    namespace = None
    repository = None
    if len(image_parts) == 3:
        registry = image_parts[-3]
    else:
        registry = "index.docker.io"
    if len(image_parts) >= 2:
        namespace = image_parts[-2]
    else:
        namespace = "library"
    repository = image_parts[-1]

    image = "/".join([registry, namespace, repository])

    try:
        if registry == "index.docker.io":
            dii = DockerHubImageInspector(namespace + "/" + repository, tag)
        else:
            dii = DockerImageInspector(registry, namespace + "/" + repository, tag)
    except HTTPError, e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
    except ConnectTimeout, e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(2)
    except Exception, e:
        sys.stderr.write("Unknown error: " + str(e) + "\n")
        sys.exit(3)

    print("Image name: %s" % dii.repository_name)
    print("Tag: %s" % dii.tag)
    print("Number of layers: %d" % len(dii.layers))
    totalSize=0
    appSize=0
    print("Sizes of layers:")
    for l in dii.layers:
        print("  %s - %s byte" % (l["digest"], l["size"]))
        totalSize += l["size"]
        if l["mediaType"] != "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip":
            appSize += l["size"]
    print("Total size (including Windows base layers): %s byte" % totalSize)
    print("Application size (w/o Windows base layers): %s byte" % appSize)
    print("Windows base image used:")
    for l in dii.layers:
        if l["mediaType"] == "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip":
            if l["digest"] in knownWindowsLayers:
                print("  %s" % knownWindowsLayers[l["digest"]])
            else:
                print("  %s - unknown Windows layer" % l["digest"])
