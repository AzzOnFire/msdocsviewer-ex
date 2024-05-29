#!/bin/bash

SDK_API="/tmp/sdk-api"
if [ ! -d "$SDK_API" ]; then
    git clone --filter=tree:0 https://github.com/MicrosoftDocs/sdk-api "$SDK_API"
fi

WDK_API="/tmp/wdk-api"
if [ ! -d "$WDK_API" ]; then
    git clone --filter=tree:0 https://github.com/MicrosoftDocs/windows-driver-docs-ddi "$WDK_API"
fi

python3 build.py /tmp/
