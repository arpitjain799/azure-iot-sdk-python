CREDENTIAL_FILE=./creds.json
DOCKER_TAG_EDGE_AGENT=1.4
DOCKER_TAG_EDGE_HUB=1.4

DOCKER_IMAGE_EDGE_AGENT="mcr.microsoft.com/azureiotedge-agent:${DOCKER_TAG_EDGE_AGENT}"
DOCKER_IMAGE_EDGE_HUB="mcr.microsoft.com/azureiotedge-hub:${DOCKER_TAG_EDGE_HUB}"

PATH_AGENT_PROPS=".modulesContent[\"\$edgeAgent\"][\"properties.desired\"]"
PATH_SYSTEM_MODULES="${PATH_AGENT_PROPS}.systemModules"
PATH_MODULES="${PATH_AGENT_PROPS}.modules"
PATH_REGISTRY_CREDENTIALS="${PATH_AGENT_PROPS}.runtime.settings.registryCredentials"

PATH_HUB_PROPS=".modulesContent[\"\$edgeHub\"][\"properties.desired\"]"
PATH_ROUTES="${PATH_HUB_PROPS}.routes"

read -d '' EMPTY_MODULE_BLOCK << EOF
{
  "version": "1.0",
  "type": "docker",
  "status": "running",
  "restartPolicy": "always",
  "settings": {
    "image": "",
    "createOptions": {}
  }
}
EOF

if [ -e ${CREDENTIAL_FILE} ]; then
    REGISTRY_USERNAME=$(jq -r .username ${CREDENTIAL_FILE})
    REGISTRY_ADDRESS=${REGISTRY_USERNAME}.azurecr.io
    REGISTRY_PASSWORD=$(jq -r .passwords[0].value ${CREDENTIAL_FILE})
    read -d '' REGISTRY_BLOCK << EOF
    {
        ${REGISTRY_USERNAME}: { 
            address: \"${REGISTRY_ADDRESS}\", 
            username: \"${REGISTRY_USERNAME}\", 
            password: \"${REGISTRY_PASSWORD}\" 
        }
    }
EOF
fi

function output_to_input_route() {
    OUTPUT_MOD=$1
    OUTPUT_NAME=$2
    INPUT_MOD=$3
    INPUT_NAME=$4

    # Quotes that end up in the final JSON need to be double-escaped (ie `\\\"`)
    echo "FROM /messages/modules/${OUTPUT_MOD}/outputs/${OUTPUT_NAME} " \
         "INTO BrokeredEndpoint(\\\\\"/modules/${INPUT_MOD}/inputs/${INPUT_NAME}\\\\\")"
}

read -d '' ROUTE_BLOCK << EOF
{
    test_to_echo: \"$(output_to_input_route testMod output1 echoMod input1)\",
    echo_to_test: \"$(output_to_input_route echoMod output2 testMod input2)\",
    default_route: \"FROM /messages/modules/testMod/* INTO \$upstream\"
}
EOF

cat deployment.template.json |\
    jq "${PATH_SYSTEM_MODULES}.edgeAgent.settings.image = \"${DOCKER_IMAGE_EDGE_AGENT}\"" |\
    jq "${PATH_SYSTEM_MODULES}.edgeHub.settings.image = \"${DOCKER_IMAGE_EDGE_HUB}\"" |\
    jq "${PATH_MODULES} = {}" |\
    jq "${PATH_MODULES}.testMod = ${EMPTY_MODULE_BLOCK}" |\
    jq "${PATH_MODULES}.testMod.settings.image = \"${REGISTRY_ADDRESS}/default-friend-module:64-v2\"" |\
    jq "${PATH_REGISTRY_CREDENTIALS} = ${REGISTRY_BLOCK}" |\
    jq "${PATH_ROUTES} = ${ROUTE_BLOCK}" 


