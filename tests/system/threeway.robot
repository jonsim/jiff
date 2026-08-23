*** Settings ***
Resource    jiff.resource
Test Template    Three-way Renderers Agree


*** Test Cases ***    DIRECTORY      EXTENSION
Independent           independent    py
Overlapping           overlapping    py
Line Shapes           line-shapes    txt
Repeated Lines        repeated       txt


*** Keywords ***
Three-way Renderers Agree
    [Documentation]    Checks both implementations draw the same three panes.
    [Arguments]    ${directory}    ${extension}
    VAR    ${root}    ${CURDIR}/../../testcases/threeway/${directory}
    VAR    @{args}
    ...    --no-color
    ...    --no-pager
    ...    -U2
    ...    ${root}/local.${extension}
    ...    ${root}/base.${extension}
    ...    ${root}/remote.${extension}

    ${python} =    Run Python Jiff    @{args}
    ${rust} =    Run Rust Jiff    @{args}

    Should Be Equal    ${python.stdout}    ${rust.stdout}
    ...    Python and Rust produced different three-way output
    Should Contain    ${python.stdout}    1: local.${extension}
    Should Contain    ${python.stdout}    2: base.${extension}
    Should Contain    ${python.stdout}    3: remote.${extension}
