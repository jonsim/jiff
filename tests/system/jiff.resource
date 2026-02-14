*** Settings ***
Library    Collections
Library    OperatingSystem
Library    Process

*** Keywords ***
Jiff Files
    [Documentation]    Runs the jiff.py script with the given left and right
    ...    files, checking the output matches the expectation file and
    ...    checks for successful execution.
    [Arguments]    ${left}    ${right}    ${expectation}    ${side_by_side}=False
    Remove Environment Variable    JIFF_DEBUG
    VAR    ${base_dir}    ${CURDIR}/../..
    VAR    @{cmd}    python3
    ...    ${base_dir}/python/jiff.py
    ...    ${base_dir}/testcases/${left}
    ...    ${base_dir}/testcases/${right}
    IF     ${side_by_side}
        Append To List    ${cmd}    --side-by-side
    END
    ${res} =    Run Process    @{cmd}
    IF    ${res.rc} != 0
        ${cmdline} =    Join Command Line    @{cmd}
        VAR    ${error}
        ...    Jiff failed with return code ${res.rc}
        ...    \n\nCommand:\n${cmdline}
        ...    \n\nStandard Output:\n${res.stdout}
        ...    \n\nStandard Error:\n${res.stderr}
        Fail    ${error}
    END
    ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
    Should Be Equal    ${res.stdout}    ${expectation_str}

Jiff Strings
    [Documentation]    Writes the left and right strings to temporary files,
    ...    then runs the Jiff Files keyword with those files and the
    ...    expectation.
    [Arguments]    ${left}    ${right}    ${expectation}
    Create File    ${TEMPDIR}/left.txt           ${left}
    Create File    ${TEMPDIR}/right.txt          ${right}
    Create File    ${TEMPDIR}/expectation.txt    ${expectation}
    Jiff Files     ${TEMPDIR}/left.txt
    ...            ${TEMPDIR}/right.txt
    ...            ${TEMPDIR}/expectation.txt
