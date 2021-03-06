import socket
from urllib import request
from xml.etree import ElementTree as ET

from sonypy.camera import Camera


SSDP_ADDR = '239.255.255.250'
SSDP_PORT = 1900
SSDP_MX = 1


discovery_msg = ('M-SEARCH * HTTP/1.1\r\n'
                 'HOST: %s:%d\r\n'
                 'MAN: "ssdp:discover"\r\n'
                 'MX: %d\r\n'
                 'ST: urn:schemas-sony-com:service:ScalarWebAPI:1\r\n'
                 '\r\n')


class Discoverer(object):
    camera_class = Camera

    @staticmethod
    def _interface_addresses(family=socket.AF_INET):
        for info in socket.getaddrinfo('', None):
            if family == info[0]:
                addr = info[-1]
                yield addr

    def _parse_ssdp_response(self, data):
        lines = data.split('\r\n')
        assert lines[0] == 'HTTP/1.1 200 OK'
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            key, val = line.split(': ', 1)
            headers[key.lower()] = val
        return headers

    def _ssdp_discover(self, timeout=30):
        socket.setdefaulttimeout(timeout)

        sock = socket.socket(socket.AF_INET,
                             socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET,
                        socket.SO_REUSEADDR,
                        1)
        sock.setsockopt(socket.IPPROTO_IP,
                        socket.IP_MULTICAST_TTL,
                        2)
        for address in self._interface_addresses():
            sock.bind(address)
            for _ in range(2):
                msg = discovery_msg % (SSDP_ADDR, SSDP_PORT, SSDP_MX)
                msg = msg.encode()
                sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))

            try:
                data = sock.recv(1024)
                data = data.decode('utf-8')
            except socket.timeout:
                print("SOCKET TIMEOUT")
                pass
            else:
                print("*****")
                print(data)
                yield self._parse_ssdp_response(data)

    def _parse_device_definition(self, doc):
        """
        Parse the XML device definition file.
        """
        services = {}

        root = ET.fromstring(doc)
        print(root.tag, root.attrib)
        # device_info_list = root[-1][-1][-1]
        device_info_list = root.find(
            '{urn:schemas-upnp-org:device-1-0}device'
            '/{urn:schemas-sony-com:av}X_ScalarWebAPI_DeviceInfo'
            '/{urn:schemas-sony-com:av}X_ScalarWebAPI_ServiceList'
        )
        print('device_info', device_info_list)
        for service in device_info_list:
            name = service.find(
                '{urn:schemas-sony-com:av}X_ScalarWebAPI_ServiceType'
            ).text
            url = service.find(
                '{urn:schemas-sony-com:av}X_ScalarWebAPI_ActionList_URL'
            ).text
            services[name] = url
            print(service)
        return services

    def _read_device_definition(self, url):
        """
        Fetch and parse the device definition, and extract the URL endpoint for
        the camera API service.
        """
        r = request.urlopen(url)
        body = r.read()
        body = body.decode('utf-8')
        services = self._parse_device_definition(body)
        return services['camera']

    def discover(self):
        endpoints = []
        for resp in self._ssdp_discover():
            url = resp['location']
            endpoint = self._read_device_definition(url)
            endpoint += '/camera'
            endpoints.append(endpoint)
        return [self.camera_class(endpoint) for endpoint in endpoints]
