# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
import base64
import json
import pytest
import requests
import urllib.parse
from azure.iot.device.edge_hsm import IoTEdgeHsm
from azure.iot.device.iot_exceptions import IoTEdgeError
from azure.iot.device import user_agent


@pytest.fixture
def edge_hsm():
    return IoTEdgeHsm(
        module_id="my_module_id",
        generation_id="module_generation_id",
        workload_uri="unix:///var/run/iotedge/workload.sock",
        api_version="my_api_version",
    )


@pytest.mark.describe("IoTEdgeHsm - Instantiation")
class TestIoTEdgeHsmInstantiation(object):
    @pytest.mark.it("URL encodes the provided module_id parameter and sets it as an attribute")
    def test_encode_and_set_module_id(self):
        module_id = "my_module_id"
        generation_id = "my_generation_id"
        api_version = "my_api_version"
        workload_uri = "unix:///var/run/iotedge/workload.sock"

        edge_hsm = IoTEdgeHsm(
            module_id=module_id,
            generation_id=generation_id,
            workload_uri=workload_uri,
            api_version=api_version,
        )

        assert edge_hsm.module_id == urllib.parse.quote(module_id, safe="")

    @pytest.mark.it(
        "Formats the provided workload_uri parameter for use with the requests library and sets it as an attribute"
    )
    @pytest.mark.parametrize(
        "workload_uri, expected_formatted_uri",
        [
            pytest.param(
                "unix:///var/run/iotedge/workload.sock",
                "http+unix://%2Fvar%2Frun%2Fiotedge%2Fworkload.sock/",
                id="Domain Socket URI",
            ),
            pytest.param("http://127.0.0.1:15580", "http://127.0.0.1:15580/", id="IP Address URI"),
        ],
    )
    def test_workload_uri_formatting(self, workload_uri, expected_formatted_uri):
        module_id = "my_module_id"
        generation_id = "my_generation_id"
        api_version = "my_api_version"

        edge_hsm = IoTEdgeHsm(
            module_id=module_id,
            generation_id=generation_id,
            workload_uri=workload_uri,
            api_version=api_version,
        )

        assert edge_hsm.workload_uri == expected_formatted_uri

    @pytest.mark.it("Sets the provided generation_id parameter as an attribute")
    def test_set_generation_id(self):
        module_id = "my_module_id"
        generation_id = "my_generation_id"
        api_version = "my_api_version"
        workload_uri = "unix:///var/run/iotedge/workload.sock"

        edge_hsm = IoTEdgeHsm(
            module_id=module_id,
            generation_id=generation_id,
            workload_uri=workload_uri,
            api_version=api_version,
        )

        assert edge_hsm.generation_id == generation_id

    @pytest.mark.it("Sets the provided api_version parameter as an attribute")
    def test_set_api_version(self):
        module_id = "my_module_id"
        generation_id = "my_generation_id"
        api_version = "my_api_version"
        workload_uri = "unix:///var/run/iotedge/workload.sock"

        edge_hsm = IoTEdgeHsm(
            module_id=module_id,
            generation_id=generation_id,
            workload_uri=workload_uri,
            api_version=api_version,
        )

        assert edge_hsm.api_version == api_version


@pytest.mark.describe("IoTEdgeHsm - .get_certificate()")
class TestIoTEdgeHsmGetCertificate(object):
    @pytest.fixture(autouse=True)
    def mock_requests_get(self, mocker):
        return mocker.patch.object(requests, "get")

    @pytest.mark.it("Sends an HTTP GET request to retrieve the trust bundle from Edge")
    async def test_requests_trust_bundle(self, mocker, edge_hsm, mock_requests_get):
        expected_url = edge_hsm.workload_uri + "trust-bundle"
        expected_params = {"api-version": edge_hsm.api_version}
        expected_headers = {
            "User-Agent": urllib.parse.quote_plus(user_agent.get_iothub_user_agent())
        }

        await edge_hsm.get_certificate()

        assert mock_requests_get.call_count == 1
        assert mock_requests_get.call_args == mocker.call(
            expected_url, params=expected_params, headers=expected_headers
        )

    @pytest.mark.it("Returns the certificate from the trust bundle received from Edge")
    async def test_returns_certificate(self, edge_hsm, mock_requests_get):
        mock_response = mock_requests_get.return_value
        certificate = "my certificate"
        mock_response.json.return_value = {"certificate": certificate}

        returned_cert = await edge_hsm.get_certificate()

        assert returned_cert is certificate

    @pytest.mark.it("Raises IoTEdgeError if a bad request is made to Edge")
    async def test_bad_request(self, edge_hsm, mock_requests_get):
        mock_response = mock_requests_get.return_value
        error = requests.exceptions.HTTPError()
        mock_response.raise_for_status.side_effect = error

        with pytest.raises(IoTEdgeError) as e_info:
            await edge_hsm.get_certificate()
        assert e_info.value.__cause__ is error

    @pytest.mark.it("Raises IoTEdgeError if there is an error in json decoding the trust bundle")
    async def test_bad_json(self, edge_hsm, mock_requests_get):
        mock_response = mock_requests_get.return_value
        error = ValueError()
        mock_response.json.side_effect = error

        with pytest.raises(IoTEdgeError) as e_info:
            await edge_hsm.get_certificate()
        assert e_info.value.__cause__ is error

    @pytest.mark.it("Raises IoTEdgeError if the certificate is missing from the trust bundle")
    async def test_bad_trust_bundle(self, edge_hsm, mock_requests_get):
        mock_response = mock_requests_get.return_value
        # Return an empty json dict with no 'certificate' key
        mock_response.json.return_value = {}

        with pytest.raises(IoTEdgeError):
            await edge_hsm.get_certificate()


@pytest.mark.describe("IoTEdgeHsm - .sign()")
class TestIoTEdgeHsmSign(object):
    @pytest.fixture(autouse=True)
    def mock_requests_post(self, mocker):
        return mocker.patch.object(requests, "post")

    @pytest.mark.it(
        "Makes an HTTP request to Edge to sign a piece of string data using the HMAC-SHA256 algorithm"
    )
    async def test_requests_data_signing(self, mocker, edge_hsm, mock_requests_post):
        data_str = "somedata"
        data_str_b64 = "c29tZWRhdGE="
        mock_requests_post.return_value.json.return_value = {"digest": "somedigest"}
        expected_url = "{workload_uri}modules/{module_id}/genid/{generation_id}/sign".format(
            workload_uri=edge_hsm.workload_uri,
            module_id=edge_hsm.module_id,
            generation_id=edge_hsm.generation_id,
        )
        expected_params = {"api-version": edge_hsm.api_version}
        expected_headers = {
            "User-Agent": urllib.parse.quote(user_agent.get_iothub_user_agent(), safe="")
        }
        expected_json = json.dumps({"keyId": "primary", "algo": "HMACSHA256", "data": data_str_b64})

        await edge_hsm.sign(data_str)

        assert mock_requests_post.call_count == 1
        assert mock_requests_post.call_args == mocker.call(
            url=expected_url, params=expected_params, headers=expected_headers, data=expected_json
        )

    @pytest.mark.it("Base64 encodes the string data in the request")
    async def test_b64_encodes_data(self, edge_hsm, mock_requests_post):
        # This test is actually implicitly tested in the first test, but it's
        # important to have an explicit test for it since it's a requirement
        data_str = "somedata"
        data_str_b64 = base64.b64encode(data_str.encode("utf-8")).decode()
        mock_requests_post.return_value.json.return_value = {"digest": "somedigest"}

        await edge_hsm.sign(data_str)

        sent_data = json.loads(mock_requests_post.call_args[1]["data"])["data"]

        assert data_str != data_str_b64
        assert sent_data == data_str_b64

    @pytest.mark.it("Returns the signed data received from Edge")
    async def test_returns_signed_data(self, edge_hsm, mock_requests_post):
        expected_digest = "somedigest"
        mock_requests_post.return_value.json.return_value = {"digest": expected_digest}

        signed_data = await edge_hsm.sign("somedata")

        assert signed_data == expected_digest

    @pytest.mark.it("Supports data strings in both string and byte formats")
    @pytest.mark.parametrize(
        "data_string, expected_request_data",
        [
            pytest.param("sign this message", "c2lnbiB0aGlzIG1lc3NhZ2U=", id="String"),
            pytest.param(b"sign this message", "c2lnbiB0aGlzIG1lc3NhZ2U=", id="Bytes"),
        ],
    )
    async def test_supported_types(
        self, edge_hsm, data_string, expected_request_data, mock_requests_post
    ):
        mock_requests_post.return_value.json.return_value = {"digest": "somedigest"}
        await edge_hsm.sign(data_string)
        sent_data = json.loads(mock_requests_post.call_args[1]["data"])["data"]

        assert sent_data == expected_request_data

    @pytest.mark.it("Raises IoTEdgeError if a bad request is made to EdgeHub")
    async def test_bad_request(self, edge_hsm, mock_requests_post):
        mock_response = mock_requests_post.return_value
        error = requests.exceptions.HTTPError()
        mock_response.raise_for_status.side_effect = error

        with pytest.raises(IoTEdgeError) as e_info:
            await edge_hsm.sign("somedata")
        assert e_info.value.__cause__ is error

    @pytest.mark.it("Raises IoTEdgeError if there is an error in json decoding the signed response")
    async def test_bad_json(self, edge_hsm, mock_requests_post):
        mock_response = mock_requests_post.return_value
        error = ValueError()
        mock_response.json.side_effect = error
        with pytest.raises(IoTEdgeError) as e_info:
            await edge_hsm.sign("somedata")
        assert e_info.value.__cause__ is error

    @pytest.mark.it("Raises IoTEdgeError if the signed data is missing from the response")
    async def test_bad_response(self, edge_hsm, mock_requests_post):
        mock_response = mock_requests_post.return_value
        mock_response.json.return_value = {}

        with pytest.raises(IoTEdgeError):
            await edge_hsm.sign("somedata")
