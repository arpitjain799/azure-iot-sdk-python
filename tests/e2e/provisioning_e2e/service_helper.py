# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
from typing import Optional

from provisioning_e2e.iothubservice20180630.iot_hub_gateway_service_ap_is20180630 import (
    IotHubGatewayServiceAPIs20180630,
)

from msrest.exceptions import HttpOperationError

# from .connection_string import ConnectionString
# from .sastoken import RenewableSasToken

from azure.iot.device.connection_string import ConnectionString
from azure.iot.device.sastoken import InternalSasTokenGenerator
from azure.iot.device.signing_mechanism import SymmetricKeySigningMechanism
import uuid
import time
import random

max_failure_count = 5

initial_backoff = 10


def connection_string_to_sas_token(conn_str):
    """
    parse an IoTHub service connection string and return the host and a shared access
    signature that can be used to connect to the given hub
    """
    conn_str_obj = ConnectionString(conn_str)
    signing_mechanism = SymmetricKeySigningMechanism(conn_str_obj.get("SharedAccessKey"))
    # signing_mechanism = sm.SymmetricKeySigningMechanism(shared_access_key)
    generator = InternalSasTokenGenerator(
        signing_mechanism=signing_mechanism, uri=conn_str_obj.get("HostName"), ttl=3600
    )
    sas_token = generator.generate_sastoken()

    # return {"host": conn_str_obj.get("HostName"), "sas": str(sas_token)}

    # conn_str_obj = ConnectionString(conn_str)
    # signing_mechanism = SymmetricKeySigningMechanism(conn_str_obj.get("SharedAccessKey"))
    # sas_token = RenewableSasToken(
    #     uri=conn_str_obj.get("HostName"),
    #     key_name=conn_str_obj.get("SharedAccessKeyName"),
    #     signing_mechanism=signing_mechanism,
    # )

    return {"host": conn_str_obj.get("HostName"), "sas": str(sas_token)}


def connection_string_to_hostname(conn_str):
    """
    Retrieves only the hostname from connection string.
    This will eventually give us the Linked IoT Hub
    """
    conn_str_obj = ConnectionString(conn_str)
    return conn_str_obj.get("HostName")


def _format_sas_uri(hostname: str, device_id: str, module_id: Optional[str]) -> str:
    """Format the SAS URI for using IoT Hub"""
    if module_id:
        return "{hostname}/devices/{device_id}/modules/{module_id}".format(
            hostname=hostname, device_id=device_id, module_id=module_id
        )
    else:
        return "{hostname}/devices/{device_id}".format(hostname=hostname, device_id=device_id)


def run_with_retry(fun, args, kwargs):
    failures_left = max_failure_count
    retry = True
    backoff = initial_backoff + random.randint(1, 10)

    while retry:
        try:
            return fun(*args, **kwargs)
        except HttpOperationError as e:
            resp = e.response.json()
            retry = False
            if "Message" in resp:
                if resp["Message"].startswith("ErrorCode:ThrottlingBacklogTimeout"):
                    retry = True
            if retry and failures_left:
                failures_left = failures_left - 1
                print("{} failures left before giving up".format(failures_left))
                print("sleeping for {} seconds".format(backoff))
                time.sleep(backoff)
                backoff = backoff * 2
            else:
                raise e


class ServiceRegistryHelper:
    def __init__(self, service_connection_string):
        self.cn = connection_string_to_sas_token(service_connection_string)
        self.service = IotHubGatewayServiceAPIs20180630("https://" + self.cn["host"]).service

    def headers(self):
        return {
            "Authorization": self.cn["sas"],
            "Request-Id": str(uuid.uuid4()),
            "User-Agent": "azure-iot-device-provisioning-e2e",
        }

    def get_device(self, device_id):
        device = run_with_retry(
            self.service.get_device, (device_id,), {"custom_headers": self.headers()}
        )
        return device

    def get_module(self, device_id, module_id):
        module = run_with_retry(
            self.service.get_module, (device_id, module_id), {"custom_headers": self.headers()}
        )
        return module

    def get_device_connection_string(self, device_id):
        device = run_with_retry(
            self.service.get_device, (device_id,), {"custom_headers": self.headers()}
        )

        primary_key = device.authentication.symmetric_key.primary_key
        return (
            "HostName="
            + self.cn["host"]
            + ";DeviceId="
            + device_id
            + ";SharedAccessKey="
            + primary_key
        )

    def get_module_connection_string(self, device_id, module_id):
        module = run_with_retry(
            self.service.get_module, (device_id, module_id), {"custom_headers": self.headers()}
        )

        primary_key = module.authentication.symmetric_key.primary_key
        return (
            "HostName="
            + self.cn["host"]
            + ";DeviceId="
            + device_id
            + ";ModuleId="
            + module_id
            + ";SharedAccessKey="
            + primary_key
        )

    def try_delete_device(self, device_id):
        try:
            run_with_retry(
                self.service.delete_device,
                (device_id,),
                {"if_match": "*", "custom_headers": self.headers()},
            )
            return True
        except HttpOperationError:
            return False

    def try_delete_module(self, device_id, module_id):
        try:
            run_with_retry(
                self.service.delete_module,
                (device_id, module_id),
                {"if_match": "*", "custom_headers": self.headers()},
            )
            return True
        except HttpOperationError:
            return False
