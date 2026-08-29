*** Settings ***
Resource         jiff.resource
Suite Setup      Build Rust Jiff
Test Template    Git Difftool Behaviour


*** Test Cases ***    COMMAND
Python                 python3    ${CURDIR}/../../python/jiff.py
Rust                   ${CURDIR}/../../target/debug/jiff


*** Keywords ***
Build Rust Jiff
    [Documentation]    Builds the executable used by the Git integration tests.
    VAR    @{command}
    ...    cargo
    ...    build
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ${result} =    Run Process    @{command}
    Process Should Succeed    ${result}    @{command}

Git Difftool Behaviour
    [Documentation]    Runs the same Git difftool scenarios against one Jiff implementation.
    [Arguments]    @{jiff_command}
    VAR    @{command}
    ...    python3
    ...    ${CURDIR}/git_difftool_tests.py
    ...    --jiff
    ...    @{jiff_command}
    ${result} =    Run Process
    ...    @{command}
    ...    env:JIFF_CONFIG=${CURDIR}/default-config.toml
    Process Should Succeed    ${result}    @{command}
