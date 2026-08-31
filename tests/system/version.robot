*** Settings ***
Resource         jiff.resource
Test Template    Version Comes From Package Metadata


*** Test Cases ***    RUNNER
Python                 Run Python Jiff
Rust                   Run Rust Jiff


*** Keywords ***
Version Comes From Package Metadata
    [Documentation]    Checks the CLI reports the package version.
    [Arguments]    ${runner}
    ${result} =    Run Keyword    ${runner}    --version
    Should Be Equal    ${result.stdout}    jiff 1.0.0
