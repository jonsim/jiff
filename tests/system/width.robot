*** Settings ***
Resource    jiff.resource


*** Test Cases ***
Two-way Output Honours Columns
    [Documentation]    Runs both implementations at 53 columns and checks neither spills over.
    VAR    ${root}    ${CURDIR}/../../testcases/minimal
    VAR    @{args}
    ...    --no-color
    ...    --no-pager
    ...    ${root}/14.txt
    ...    ${root}/15.txt

    Outputs Agree At Width    53    @{args}

Three-way Output Honours Columns
    [Documentation]    Applies the same captured width to all three panes.
    VAR    ${root}    ${CURDIR}/../../testcases/threeway/overlapping
    VAR    @{args}
    ...    --no-color
    ...    --no-pager
    ...    --no-syntax
    ...    ${root}/local.py
    ...    ${root}/base.py
    ...    ${root}/remote.py

    Outputs Agree At Width    53    @{args}


*** Keywords ***
Outputs Agree At Width
    [Documentation]    Checks byte parity and the longest rendered line.
    [Arguments]    ${width}    @{args}
    ${python} =    Run Python Jiff At Width    ${width}    @{args}
    ${rust} =    Run Rust Jiff At Width    ${width}    @{args}

    Should Be Equal    ${python.stdout}    ${rust.stdout}
    ${longest_line} =    Evaluate
    ...    max(map(len, $python.stdout.splitlines()), default=0)
    Should Be True    ${longest_line} <= ${width}
