# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

from ..service_helper import ServiceRegistryHelper, connection_string_to_hostname
from provisioningserviceclient import ProvisioningServiceClient, IndividualEnrollment
from provisioningserviceclient.protocol.models import AttestationMechanism, ReprovisionPolicy
import pytest
import logging
import os
import uuid

from azure.iot.device import ProvisioningSession

logging.basicConfig(level=logging.DEBUG)


PROVISIONING_HOST = os.getenv("PROVISIONING_DEVICE_ENDPOINT")
ID_SCOPE = os.getenv("PROVISIONING_DEVICE_IDSCOPE")
conn_str = os.getenv("PROVISIONING_SERVICE_CONNECTION_STRING")
service_client = ProvisioningServiceClient.create_from_connection_string(
    os.getenv("PROVISIONING_SERVICE_CONNECTION_STRING")
)
service_client = ProvisioningServiceClient.create_from_connection_string(conn_str)
device_registry_helper = ServiceRegistryHelper(os.getenv("IOTHUB_CONNECTION_STRING"))
linked_iot_hub = connection_string_to_hostname(os.getenv("IOTHUB_CONNECTION_STRING"))


@pytest.mark.it(
    "A device gets provisioned to the linked IoTHub with the device_id equal to the registration_id"
    "of the individual enrollment that has been created with a symmetric key authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_device_register_with_no_device_id_for_a_symmetric_key_individual_enrollment(
    protocol,
):
    try:
        individual_enrollment_record = create_individual_enrollment(
            "e2e-dps-legilimens" + str(uuid.uuid4())
        )

        registration_id = individual_enrollment_record.registration_id
        symmetric_key = individual_enrollment_record.attestation.symmetric_key.primary_key

        registration_result = await result_from_register(registration_id, symmetric_key, protocol)

        assert registration_result is not None
        assert_device_provisioned(
            device_id=registration_id, registration_result=registration_result
        )
        device_registry_helper.try_delete_device(registration_id)
    finally:
        service_client.delete_individual_enrollment_by_param(registration_id)


@pytest.mark.it(
    "A device gets provisioned to the linked IoTHub with the user supplied device_id different from the registration_id of the individual enrollment that has been created with a symmetric key authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_device_register_with_device_id_for_a_symmetric_key_individual_enrollment(protocol):

    device_id = "e2edpsgoldensnitch"
    try:
        individual_enrollment_record = create_individual_enrollment(
            registration_id="e2e-dps-levicorpus" + str(uuid.uuid4()), device_id=device_id
        )

        registration_id = individual_enrollment_record.registration_id
        symmetric_key = individual_enrollment_record.attestation.symmetric_key.primary_key

        registration_result = await result_from_register(registration_id, symmetric_key, protocol)

        assert registration_result is not None
        assert device_id != registration_id
        assert_device_provisioned(device_id=device_id, registration_result=registration_result)
        device_registry_helper.try_delete_device(device_id)
    finally:
        service_client.delete_individual_enrollment_by_param(registration_id)


def create_individual_enrollment(registration_id, device_id=None):
    """
    Create an individual enrollment record using the service client
    :param registration_id: The registration id of the enrollment
    :param device_id:  Optional device id
    :return: And individual enrollment record
    """
    reprovision_policy = ReprovisionPolicy(migrate_device_data=True)
    attestation_mechanism = AttestationMechanism(type="symmetricKey")

    individual_provisioning_model = IndividualEnrollment.create(
        attestation=attestation_mechanism,
        registration_id=registration_id,
        device_id=device_id,
        reprovision_policy=reprovision_policy,
    )

    return service_client.create_or_update(individual_provisioning_model)


def assert_device_provisioned(device_id, registration_result):
    """
    Assert that the device has been provisioned correctly to iothub from the registration result as well as from the device registry
    :param device_id: The device id
    :param registration_result: The registration result
    """
    print(registration_result)
    assert registration_result["status"] == "assigned"
    assert registration_result["registrationState"]["deviceId"] == device_id
    assert registration_result["registrationState"]["assignedHub"] == linked_iot_hub

    device = device_registry_helper.get_device(device_id)
    assert device is not None
    assert device.authentication.type == "sas"
    assert device.device_id == device_id


async def result_from_register(registration_id, symmetric_key, protocol):
    # We have this mapping because the pytest logs look better with "mqtt" and "mqttws"
    # instead of just "True" and "False".
    protocol_boolean_mapping = {"mqtt": False, "mqttws": True}
    async with ProvisioningSession(
        provisioning_host=PROVISIONING_HOST,
        registration_id=registration_id,
        id_scope=ID_SCOPE,
        shared_access_key=symmetric_key,
        websockets=protocol_boolean_mapping[protocol],
    ) as session:
        result = await session.register()
    return result if result is not None else None
