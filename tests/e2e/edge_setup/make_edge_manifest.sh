DOCKER_TAG_EDGE_AGENT=1.4
DOCKER_TAG_EDGE_HUB=1.4

DOCKER_IMAGE_EDGE_AGENT="mcr.microsoft.com/azureiotedge-agent:${DOCKER_TAG_EDGE_AGENT}"
DOCKER_IMAGE_EDGE_HUB="mcr.microsoft.com/azureiotedge-hub:${DOCKER_TAG_EDGE_HUB}"

PATH_SYSTEM_MODULES=".modulesContent[\"\$edgeAgent\"][\"properties.desired\"].systemModules"
PATH_MODULES=".modulesContent[\"\$edgeAgent\"][\"properties.desired\"].modules"
PATH_ROUTES=".modulesContent[\"\$edgeHub\"][\"properties.desired\"].routes"
read -d '' CONTENT_EMPTY_MODULE << EOF
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

function output_to_input_route() {
    OUTPUT_MOD=$1
    OUTPUT_NAME=$2
    INPUT_MOD=$3
    INPUT_NAME=$4

    echo "FROM /messages/modules/${OUTPUT_MOD}/outputs/${OUTPUT_NAME} " \
         "INTO BrokeredEndpoint(\\\"/modules/${INPUT_MOD}/inputs/${INPUT_NAME}\\\")"
}

cat deployment.template.json |\
    jq "${PATH_SYSTEM_MODULES}.edgeAgent.settings.image = \"${DOCKER_IMAGE_EDGE_AGENT}\"" |\
    jq "${PATH_SYSTEM_MODULES}.edgeHub.settings.image = \"${DOCKER_IMAGE_EDGE_HUB}\"" |\
    jq "${PATH_MODULES} = {}" |\
    jq "${PATH_MODULES}.foo = ${CONTENT_EMPTY_MODULE}" |\
    jq "${PATH_ROUTES} = { \
        test_to_echo: \"$(output_to_input_route testMod output1 echoMod input1)\", \
        echo_to_test: \"$(output_to_input_route echoMod output2 testMod input2)\", \
        default_route: \"FROM /messages/modules/testMod/* INTO \$upstream\" \
    }"

