*** Settings ***
Resource         jiff.resource
Suite Setup      Build Rust Jiff For Pager Tests
Test Template    Pager Behaviour


*** Test Cases ***    COMMAND
Python                 python3    ${CURDIR}/../../python/jiff.py
Rust                   ${CURDIR}/../../target/debug/jiff


*** Keywords ***
Build Rust Jiff For Pager Tests
    [Documentation]    Builds the executable used inside the pseudo-terminal.
    VAR    @{command}
    ...    cargo
    ...    build
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ${result} =    Run Process    @{command}
    Process Should Succeed    ${result}    @{command}

Pager Behaviour
    [Documentation]    Exercises the real pager process for one implementation.
    [Arguments]    @{jiff_command}
    VAR    @{command}
    ...    python3
    ...    ${CURDIR}/pager_tests.py
    ...    --jiff
    ...    @{jiff_command}
    ${result} =    Run Process    @{command}
    Process Should Succeed    ${result}    @{command}
