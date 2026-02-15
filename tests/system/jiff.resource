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
    VAR    ${base_dir}    ${CURDIR}/../..
    VAR    @{args}
    ...    ${base_dir}/testcases/${left}
    ...    ${base_dir}/testcases/${right}
    IF     ${side_by_side}
        Append To List    ${args}    --side-by-side
    END
    # Check the Python implementation's output.
    ${res} =    Run Python Jiff    @{args}
    ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
    Should Be Equal    ${res.stdout}    ${expectation_str}    Python implementation produced incorrect output

    # Check the Rust implementation's output.
    ${res} =    Run Rust Jiff    @{args}
    ${expectation_str} =    Get File    ${base_dir}/testcases/${expectation}
    Should Be Equal    ${res.stdout}    ${expectation_str}    Rust implementation produced incorrect output


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

Run Python Jiff
    [Documentation]    Runs the Python version of `jiff` with the given
    ...    arguments, checks for successful execution and returns the result
    ...    object.
    [Arguments]    @{args}
    Remove Environment Variable    JIFF_DEBUG
    VAR    @{cmd}    python3
    ...    ${CURDIR}/../../python/jiff.py
    ...    @{args}
    ${res} =    Run Process Check Output   @{cmd}
    RETURN    ${res}

Run Rust Jiff
    [Documentation]    Runs the Rust version of `jiff` with the given
    ...    arguments, checks for successful execution and returns the result
    ...    object.
    [Arguments]    @{args}
    Remove Environment Variable    JIFF_DEBUG
    VAR    @{cmd}    cargo
    ...    run
    ...    --manifest-path=${CURDIR}/../../Cargo.toml
    ...    --
    ...    @{args}
    ${res} =    Run Process Check Output    @{cmd}
    RETURN    ${res}

Run Process Check Output
    [Documentation]    Runs a process with the given command and arguments,
    ...    checks for successful execution and returns the result object.
    [Arguments]    @{cmd}
    ${res} =    Run Process    @{cmd}
    IF    ${res.rc} != 0
        ${cmdline} =    Join Command Line    @{cmd}
        VAR    ${error}
        ...    Process failed with return code ${res.rc}
        ...    \n\nCommand:\n${cmdline}
        ...    \n\nStandard Output:\n${res.stdout}
        ...    \n\nStandard Error:\n${res.stderr}
        Fail    ${error}
    END
    RETURN    ${res}
