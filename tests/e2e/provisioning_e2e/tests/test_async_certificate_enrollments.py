# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------


from ..service_helper import ServiceRegistryHelper, connection_string_to_hostname
from azure.iot.device import ProvisioningSession

from provisioningserviceclient import (
    ProvisioningServiceClient,
    IndividualEnrollment,
    EnrollmentGroup,
)
from provisioningserviceclient.protocol.models import AttestationMechanism, ReprovisionPolicy
import pytest
import logging
import os
import uuid
import ssl
from . import path_adjust  # noqa: F401

# Refers to an item in "scripts" in the root. This is made to work via the above path_adjust
from scripts.create_x509_chain_crypto import (
    before_cert_creation_from_pipeline,
    call_intermediate_cert_and_device_cert_creation_from_pipeline,
    delete_directories_certs_created_from_pipeline,
)


logging.basicConfig(level=logging.DEBUG)


intermediate_common_name = "e2edpshomenum"
intermediate_password = "revelio"
device_common_name = "e2edpslocomotor" + str(uuid.uuid4())
device_password = "mortis"

service_client = ProvisioningServiceClient.create_from_connection_string(
    os.getenv("PROVISIONING_SERVICE_CONNECTION_STRING")
)
device_registry_helper = ServiceRegistryHelper(os.getenv("IOTHUB_CONNECTION_STRING"))
linked_iot_hub = connection_string_to_hostname(os.getenv("IOTHUB_CONNECTION_STRING"))

PROVISIONING_HOST = os.getenv("PROVISIONING_DEVICE_ENDPOINT")
ID_SCOPE = os.getenv("PROVISIONING_DEVICE_IDSCOPE")

certificate_count = 8
type_to_device_indices = {
    "individual_with_device_id": [1],
    "individual_no_device_id": [2],
    "group_intermediate": [3, 4, 5],
    "group_ca": [6, 7, 8],
}


@pytest.fixture(scope="module", autouse=True)
def before_all_tests(request):
    logging.info("set up certificates before cert related tests")
    before_cert_creation_from_pipeline()
    call_intermediate_cert_and_device_cert_creation_from_pipeline(
        intermediate_common_name=intermediate_common_name,
        device_common_name=device_common_name,
        ca_password=os.getenv("PROVISIONING_ROOT_PASSWORD"),
        intermediate_password=intermediate_password,
        device_password=device_password,
        device_count=8,
    )

    def after_module():
        logging.info("tear down certificates after cert related tests")
        delete_directories_certs_created_from_pipeline()

    request.addfinalizer(after_module)


@pytest.mark.it(
    "A device gets provisioned to the linked IoTHub with the user supplied device_id different from the registration_id of the individual enrollment that has been created with a selfsigned X509 authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_device_register_with_device_id_for_a_x509_individual_enrollment(protocol):
    device_id = "e2edpsthunderbolt"
    device_index = type_to_device_indices.get("individual_with_device_id")[0]

    try:
        individual_enrollment_record = create_individual_enrollment_with_x509_client_certs(
            device_index=device_index, device_id=device_id
        )
        registration_id = individual_enrollment_record.registration_id

        device_cert_file = "demoCA/newcerts/device_cert" + str(device_index) + ".pem"
        device_key_file = "demoCA/private/device_key" + str(device_index) + ".pem"
        registration_result = await result_from_register(
            registration_id, device_cert_file, device_key_file, protocol
        )

        assert registration_result is not None
        assert device_id != registration_id
        assert_device_provisioned(device_id=device_id, registration_result=registration_result)
        device_registry_helper.try_delete_device(device_id)
    finally:
        service_client.delete_individual_enrollment_by_param(registration_id)


@pytest.mark.it(
    "A device gets provisioned to the linked IoTHub with device_id equal to the registration_id of the individual enrollment that has been created with a selfsigned X509 authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_device_register_with_no_device_id_for_a_x509_individual_enrollment(protocol):
    device_index = type_to_device_indices.get("individual_no_device_id")[0]

    try:
        individual_enrollment_record = create_individual_enrollment_with_x509_client_certs(
            device_index=device_index
        )
        registration_id = individual_enrollment_record.registration_id

        device_cert_file = "demoCA/newcerts/device_cert" + str(device_index) + ".pem"
        device_key_file = "demoCA/private/device_key" + str(device_index) + ".pem"
        registration_result = await result_from_register(
            registration_id, device_cert_file, device_key_file, protocol
        )

        assert registration_result is not None
        assert_device_provisioned(
            device_id=registration_id, registration_result=registration_result
        )
        device_registry_helper.try_delete_device(registration_id)
    finally:
        service_client.delete_individual_enrollment_by_param(registration_id)


@pytest.mark.it(
    "A group of devices get provisioned to the linked IoTHub with device_ids equal to the individual registration_ids inside a group enrollment that has been created with intermediate X509 authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_group_of_devices_register_with_no_device_id_for_a_x509_intermediate_authentication_group_enrollment(
    protocol,
):
    group_id = "e2e-intermediate-durmstrang" + str(uuid.uuid4())
    common_device_id = device_common_name
    devices_indices = type_to_device_indices.get("group_intermediate")
    device_count_in_group = len(devices_indices)
    reprovision_policy = ReprovisionPolicy(migrate_device_data=True)

    try:
        intermediate_cert_filename = "demoCA/newcerts/intermediate_cert.pem"
        with open(intermediate_cert_filename, "r") as intermediate_pem:
            intermediate_cert_content = intermediate_pem.read()

        attestation_mechanism = AttestationMechanism.create_with_x509_signing_certs(
            intermediate_cert_content
        )
        enrollment_group_provisioning_model = EnrollmentGroup.create(
            group_id, attestation=attestation_mechanism, reprovision_policy=reprovision_policy
        )

        service_client.create_or_update(enrollment_group_provisioning_model)

        count = 0
        common_device_key_input_file = "demoCA/private/device_key"
        common_device_cert_input_file = "demoCA/newcerts/device_cert"
        common_device_inter_cert_chain_file = "demoCA/newcerts/out_inter_device_chain_cert"
        for index in devices_indices:
            count = count + 1
            device_id = common_device_id + str(index)
            device_key_input_file = common_device_key_input_file + str(index) + ".pem"
            device_cert_input_file = common_device_cert_input_file + str(index) + ".pem"
            device_inter_cert_chain_file = common_device_inter_cert_chain_file + str(index) + ".pem"
            filenames = [device_cert_input_file, intermediate_cert_filename]
            with open(device_inter_cert_chain_file, "w") as outfile:
                for fname in filenames:
                    with open(fname) as infile:
                        outfile.write(infile.read())

            registration_result = await result_from_register(
                registration_id=device_id,
                device_cert_file=device_inter_cert_chain_file,
                device_key_file=device_key_input_file,
                protocol=protocol,
            )

            assert registration_result is not None
            assert_device_provisioned(device_id=device_id, registration_result=registration_result)
            device_registry_helper.try_delete_device(device_id)

        # Make sure space is okay. The following line must be outside for loop.
        assert count == device_count_in_group

    finally:
        service_client.delete_enrollment_group_by_param(group_id)


@pytest.mark.skip(
    reason="The enrollment is never properly created on the pipeline and it is always created without any CA reference and eventually the registration fails"
)
@pytest.mark.it(
    "A group of devices get provisioned to the linked IoTHub with device_ids equal to the individual registration_ids inside a group enrollment that has been created with an already uploaded ca cert X509 authentication"
)
@pytest.mark.parametrize("protocol", ["mqtt", "mqttws"])
async def test_group_of_devices_register_with_no_device_id_for_a_x509_ca_authentication_group_enrollment(
    protocol,
):
    group_id = "e2e-ca-ilvermorny" + str(uuid.uuid4())
    common_device_id = device_common_name
    devices_indices = type_to_device_indices.get("group_ca")
    device_count_in_group = len(devices_indices)
    reprovision_policy = ReprovisionPolicy(migrate_device_data=True)

    try:
        DPS_GROUP_CA_CERT = os.getenv("PROVISIONING_ROOT_CERT")
        attestation_mechanism = AttestationMechanism.create_with_x509_ca_refs(
            ref1=DPS_GROUP_CA_CERT
        )
        enrollment_group_provisioning_model = EnrollmentGroup.create(
            group_id, attestation=attestation_mechanism, reprovision_policy=reprovision_policy
        )

        service_client.create_or_update(enrollment_group_provisioning_model)

        count = 0
        intermediate_cert_filename = "demoCA/newcerts/intermediate_cert.pem"
        common_device_key_input_file = "demoCA/private/device_key"
        common_device_cert_input_file = "demoCA/newcerts/device_cert"
        common_device_inter_cert_chain_file = "demoCA/newcerts/out_inter_device_chain_cert"
        for index in devices_indices:
            count = count + 1
            device_id = common_device_id + str(index)
            device_key_input_file = common_device_key_input_file + str(index) + ".pem"
            device_cert_input_file = common_device_cert_input_file + str(index) + ".pem"
            device_inter_cert_chain_file = common_device_inter_cert_chain_file + str(index) + ".pem"
            filenames = [device_cert_input_file, intermediate_cert_filename]
            with open(device_inter_cert_chain_file, "w") as outfile:
                for fname in filenames:
                    with open(fname) as infile:
                        logging.debug("Filename is {}".format(fname))
                        content = infile.read()
                        logging.debug(content)
                        outfile.write(content)

            registration_result = await result_from_register(
                registration_id=device_id,
                device_cert_file=device_inter_cert_chain_file,
                device_key_file=device_key_input_file,
                protocol=protocol,
            )
            assert registration_result is not None
            assert_device_provisioned(device_id=device_id, registration_result=registration_result)
            device_registry_helper.try_delete_device(device_id)

        # Make sure space is okay. The following line must be outside for loop.
        assert count == device_count_in_group
    finally:
        service_client.delete_enrollment_group_by_param(group_id)


def assert_device_provisioned(device_id, registration_result):
    """
    Assert that the device has been provisioned correctly to iothub from the registration result as well as from the device registry
    :param device_id: The device id
    :param registration_result: The registration result
    """
    assert registration_result["status"] == "assigned"
    assert registration_result["registrationState"]["deviceId"] == device_id
    assert registration_result["registrationState"]["assignedHub"] == linked_iot_hub

    device = device_registry_helper.get_device(device_id)
    assert device is not None
    assert device.authentication.type == "selfSigned"
    assert device.device_id == device_id


def create_individual_enrollment_with_x509_client_certs(device_index, device_id=None):
    registration_id = device_common_name + str(device_index)
    reprovision_policy = ReprovisionPolicy(migrate_device_data=True)

    device_cert_input_file = "demoCA/newcerts/device_cert" + str(device_index) + ".pem"
    with open(device_cert_input_file, "r") as in_device_cert:
        device_cert_content = in_device_cert.read()

    attestation_mechanism = AttestationMechanism.create_with_x509_client_certs(device_cert_content)

    individual_provisioning_model = IndividualEnrollment.create(
        attestation=attestation_mechanism,
        registration_id=registration_id,
        reprovision_policy=reprovision_policy,
        device_id=device_id,
    )

    return service_client.create_or_update(individual_provisioning_model)


async def result_from_register(registration_id, device_cert_file, device_key_file, protocol):
    # We have this mapping because the pytest logs look better with "mqtt" and "mqttws"
    # instead of just "True" and "False".
    protocol_boolean_mapping = {"mqtt": False, "mqttws": True}
    ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.check_hostname = True
    ssl_context.load_default_certs()
    ssl_context.load_cert_chain(
        certfile=device_cert_file,
        keyfile=device_key_file,
        password=device_password,
    )

    async with ProvisioningSession(
        provisioning_host=PROVISIONING_HOST,
        registration_id=registration_id,
        id_scope=ID_SCOPE,
        ssl_context=ssl_context,
        websockets=protocol_boolean_mapping[protocol],
    ) as session:
        print("Connected")
        properties = {"Type": "Apple", "Sweet": True, "count": 5}
        result = await session.register(payload=properties)
        print("Finished provisioning")
        print(result)
        result = await session.register()
    return result if result is not None else None
